# render_layer_tool/model.py
# -*- coding: utf-8 -*-
import maya.cmds as cmds
import logging
import traceback
import re

logging.basicConfig()
log = logging.getLogger(__name__)
log.setLevel(logging.INFO) # 通常はINFOレベルに設定

try:
    import maya.app.renderSetup.model.renderSetup as rs
    import maya.app.renderSetup.model.override as override
    import maya.app.renderSetup.model.selector as selector
    try:
        import maya.app.renderSetup.model.renderSetupInternal as rsInternal
    except ImportError:
        rsInternal = None
except ImportError:
    rs = None
    log.error("Maya Render Setup API not found. Tool cannot function.")

class RenderLayerManager:
    def __init__(self):
        if rs is None: raise EnvironmentError("Render Setup API is not available.")
        self.rs_instance = rs.instance()
        self.AOV_PRESETS = {
            "Basic": ["diffuse", "specular", "N", "P"],
            "Full Beauty": ["diffuse", "specular", "coat", "transmission", "sss", "volume", "emission", "background"],
            "Utility": ["id", "shadow_matte", "N", "P", "AO"],
            "Clear": []
        }

    def get_aov_preset(self, preset_name):
        return self.AOV_PRESETS.get(preset_name, [])

    def list_render_layers(self):
        try:
            layers = self.rs_instance.getRenderLayers()
            default_layer = self.rs_instance.getDefaultRenderLayer()
            return sorted([layer.name() for layer in layers if layer and layer != default_layer])
        except Exception as e:
            log.error(f"レンダーレイヤーのリストアップ中にエラー: {e}")
            return []

    def _sanitize_name(self, name):
        cleaned_name = name.split('|')[-1].split(':')[-1]
        sanitized = re.sub(r'[^a-zA-Z0-9_]', '_', cleaned_name)
        if not sanitized: sanitized = "Unnamed"
        elif sanitized[0].isdigit(): sanitized = "Object_" + sanitized
        if not sanitized.startswith("RL_"): sanitized = "RL_" + sanitized
        return sanitized

    def create_render_layers(self, base_name, target_list, pvoff_list, settings):
        create_each = settings.get('create_each', False)
        layers_to_create = []
        if create_each:
            if not target_list: raise ValueError("個別作成モードでは、対象リストに最低1つのオブジェクトが必要です。")
            for obj in target_list: layers_to_create.append((self._sanitize_name(obj), [obj]))
        else:
            final_base_name = base_name.strip() or (target_list and target_list[0]) or (pvoff_list and "Scene_PVOff") or "Scene"
            layers_to_create.append((self._sanitize_name(final_base_name), target_list))

        existing_layer_names = set(self.list_render_layers())
        created_count = 0
        try:
            if rsInternal:
                with rsInternal.deferredEvaluation(True):
                    created_count = self._execute_layer_creation(layers_to_create, existing_layer_names, pvoff_list, settings)
            else:
                created_count = self._execute_layer_creation(layers_to_create, existing_layer_names, pvoff_list, settings)
        except Exception as e:
            log.error(f"レイヤー作成バッチ処理中にエラーが発生しました: {e}")
            raise
        return created_count

    def _execute_layer_creation(self, layers_to_create, existing_layer_names, pvoff_list, settings):
        created_count = 0
        for layer_name_base, targets in layers_to_create:
            final_layer_name = layer_name_base
            counter = 1
            while final_layer_name in existing_layer_names or cmds.objExists(final_layer_name):
                 final_layer_name = f"{layer_name_base}_{counter}"
                 counter += 1
            if self._create_single_layer_structure(final_layer_name, targets, pvoff_list, settings):
                created_count += 1
                existing_layer_names.add(final_layer_name)
        return created_count

    # 【ロジック変更】ユーザー様の意図に合わせてコレクション作成の順序と条件を変更
    def _create_single_layer_structure(self, layer_name, target_objects, pvoff_objects, settings):
        auto_matte = settings.get('auto_matte', False)
        aov_settings = settings.get('aov_settings', {})
        layer = None
        try:
            layer = self.rs_instance.createRenderLayer(layer_name)
            if not layer: raise RuntimeError(f"Render Layer object creation returned None for {layer_name}")

            valid_targets = [obj for obj in target_objects if cmds.objExists(obj)]
            valid_pvoffs = [obj for obj in pvoff_objects if cmds.objExists(obj)]
            
            # --- 意図に合わせたロジック ---
            # 1. TargetとPVOffコレクションは常に作成する
            if valid_targets:
                target_col = layer.createCollection(f"COL_{layer_name}_Target")
                target_col.getSelector().staticSelection.set(valid_targets)

            if valid_pvoffs:
                pvoff_col = layer.createCollection(f"COL_{layer_name}_PVOff")
                pvoff_col.getSelector().staticSelection.set(valid_pvoffs)
                self._apply_primary_visibility_override(pvoff_col, enabled=False)

            # 2. auto_matteがオンの場合のみ、ワールド全体を操作するコレクションを追加で作成
            if auto_matte:
                # ワールド全体を非表示にする
                world_matte_col = layer.createCollection(f"COL_{layer_name}_WorldMatte")
                world_matte_col.getSelector().setPattern('*')
                self._apply_primary_visibility_override(world_matte_col, enabled=False)

                # TargetとPVOffのオブジェクトだけ表示を戻す（優先度を上書き）
                all_visible_objects = list(set(valid_targets) | set(valid_pvoffs))
                if all_visible_objects:
                    visible_col = layer.createCollection(f"COL_{layer_name}_Visible")
                    visible_col.getSelector().staticSelection.set(all_visible_objects)
                    self._apply_primary_visibility_override(visible_col, enabled=True)
            
            self._setup_aov_overrides(layer, aov_settings)
            return True

        except Exception as e:
            log.error(f"レンダーレイヤー構造の作成中にエラーが発生しました ({layer_name}): {traceback.format_exc()}")
            if layer: self._cleanup_failed_layer(layer)
            return False

    # 【不具合修正】setAttrValueの代わりにcmds.setAttrを使用
    def _apply_primary_visibility_override(self, parent_collection, enabled=True):
        try:
            shapes_col = parent_collection.createCollection(f"{parent_collection.name()}_Shapes")
            shapes_col.getSelector().setPattern('*')
            if hasattr(selector.Filters, 'kShapes'):
                shapes_col.getSelector().setFilterType(selector.Filters.kShapes)
            
            ov_name = f"OVR_PV_{'On' if enabled else 'Off'}"
            pv_override = shapes_col.createOverride(ov_name, override.AbsOverride.kTypeId)
            
            if pv_override:
                pv_override.setAttributeName("primaryVisibility")
                
                # --- ここからが修正箇所 ---
                # 不安定なsetAttrValueを避け、cmds.setAttrで直接値を設定する
                # pv_override.setAttrValue(enabled) の代替
                override_node_name = pv_override.name()
                attribute_plug = f"{override_node_name}.attrValue"
                cmds.setAttr(attribute_plug, enabled)
                # --- 修正箇所ここまで ---

            else:
                raise RuntimeError("createOverride returned None, failed to create override.")

        except Exception as e:
            log.error(f"Primary Visibility overrideの適用に失敗: {e} @ {parent_collection.name()}")
            cmds.warning(f"自動マット化機能がコレクション '{parent_collection.name()}' で失敗しました。")

    def _setup_aov_overrides(self, layer, aov_settings):
        if not cmds.pluginInfo('mtoa', query=True, loaded=True): return
        try:
            # (省略 - 変更なし)
            pass 
        except Exception as e:
            log.error(f"AOVオーバーライドの適用中にエラーが発生しました: {e}")

    def _cleanup_failed_layer(self, layer):
        if not layer or not cmds.objExists(layer.name()): return
        try:
            cmds.delete(layer.name())
        except Exception as e:
            log.error(f"レイヤーのクリーンアップに失敗: {e}")

    def delete_render_layer(self, layer_name):
        try:
            if cmds.objExists(layer_name) and layer_name != "defaultRenderLayer":
                cmds.delete(layer_name)
                return True
            return False
        except Exception as e:
            log.warning(f"レイヤー '{layer_name}' の削除中に予期せぬエラーが発生: {e}")
            return False

    def delete_multiple_layers(self, layer_names):
        count = 0
        for name in layer_names:
            if self.delete_render_layer(name):
                count += 1
        return count

    def get_layer_contents(self, layer_name):
        if not layer_name: return None
        layer = self.rs_instance.getRenderLayer(layer_name)
        if not layer: raise ValueError(f"Render layer '{layer_name}' not found.")
        contents = {"Target": [], "PVOff": [], "Visible": [], "WorldMatte": []}
        for col in layer.getCollections():
            key, col_name = None, col.name()
            if "_Target" in col_name: key = "Target"
            elif "_PVOff" in col_name: key = "PVOff"
            elif "_Visible" in col_name: key = "Visible"
            elif "_WorldMatte" in col_name: key = "WorldMatte"
            if key:
                try:
                    static_selection_list = list(col.getSelector().staticSelection)
                    if static_selection_list: contents[key].extend(static_selection_list)
                except Exception as e:
                    log.warning(f"Could not get members from collection {col_name}: {e}")
        return {k: sorted(list(set(v))) for k, v in contents.items() if v}