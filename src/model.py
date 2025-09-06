# render_layer_tool/model.py
# -*- coding: utf-8 -*-
import maya.cmds as cmds
import logging
import traceback
import re

# Render Setup APIのインポート
try:
    import maya.app.renderSetup.model.renderSetup as rs
    import maya.app.renderSetup.model.override as override
    import maya.app.renderSetup.model.selector as selector
    try:
        import maya.app.renderSetup.model.renderSetupInternal as rsInternal
    except ImportError:
        rsInternal = None
        logging.info("maya.app.renderSetup.model.renderSetupInternal not found.")
except ImportError:
    rs = None
    logging.error("Maya Render Setup API not found. Tool cannot function.")

class RenderLayerManager:
    """
    レンダーレイヤー、コレクション、オーバーライドの作成と管理。
    """
    def __init__(self):
        if rs is None:
            raise EnvironmentError("Render Setup API is not available.")
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
            logging.error(f"レンダーレイヤーのリストアップ中にエラー: {e}")
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
            logging.error(f"レイヤー作成バッチ処理中にエラーが発生しました: {e}")
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

    def _create_single_layer_structure(self, layer_name, target_objects, pvoff_objects, settings):
        auto_matte = settings.get('auto_matte', False) # デフォルトをFalseに変更
        aov_settings = settings.get('aov_settings', {})
        layer = None
        try:
            layer = self.rs_instance.createRenderLayer(layer_name)
            if not layer: raise RuntimeError(f"Render Layer object creation returned None for {layer_name}")

            valid_targets = [obj for obj in target_objects if cmds.objExists(obj)]
            valid_pvoffs = [obj for obj in pvoff_objects if cmds.objExists(obj)]
            all_valid_objects = list(set(valid_targets) | set(valid_pvoffs))

            # 【修正】自動マット化がオンの場合のみ、不安定な処理を実行する
            if auto_matte:
                world_matte_col = layer.createCollection(f"COL_{layer_name}_WorldMatte")
                world_matte_col.getSelector().setPattern('*')
                self._apply_primary_visibility_override(world_matte_col, enabled=False)
                if all_valid_objects:
                    visible_col = layer.createCollection(f"COL_{layer_name}_Visible")
                    visible_col.getSelector().staticSelection.set(all_valid_objects)
                    self._apply_primary_visibility_override(visible_col, enabled=True)
            
            if valid_targets:
                target_col = layer.createCollection(f"COL_{layer_name}_Target")
                target_col.getSelector().staticSelection.set(valid_targets)
            if valid_pvoffs:
                pvoff_col = layer.createCollection(f"COL_{layer_name}_PVOff")
                pvoff_col.getSelector().staticSelection.set(valid_pvoffs)
                # PVOffリストのオブジェクトはauto_matteがオフでもPVをオフにする
                self._apply_primary_visibility_override(pvoff_col, enabled=False)

            self._setup_aov_overrides(layer, aov_settings)
            return True

        except Exception as e:
            logging.error(f"レンダーレイヤー構造の作成中にエラーが発生しました ({layer_name}): {e}")
            traceback.print_exc()
            if layer: self._cleanup_failed_layer(layer)
            return False

    def _apply_primary_visibility_override(self, parent_collection, enabled=True):
        try:
            shapes_col = parent_collection.createCollection(f"{parent_collection.name()}_Shapes")
            shapes_col.getSelector().setPattern('*')
            if hasattr(selector.Filters, 'kShapes'):
                shapes_col.getSelector().setFilterType(selector.Filters.kShapes)
            
            # フォールバック方式のみ使用（こちらの方がまだ安定している可能性にかける）
            ov_name = f"OVR_PV_{'On' if enabled else 'Off'}"
            pv_override = shapes_col.createOverride(ov_name, override.AbsOverride.kTypeId)
            if pv_override:
                pv_override.setAttributeName("primaryVisibility")
                pv_override.setAttrValue(enabled)
            else:
                raise RuntimeError("createOverride returned None.")
        except Exception as e:
            logging.error(f"Primary Visibility overrideの適用に失敗: {e} @ {parent_collection.name()}")
            cmds.warning(f"自動マット化機能がコレクション '{parent_collection.name()}' で失敗しました。")

    def _setup_aov_overrides(self, layer, aov_settings):
        # (この関数は変更なし)
        if not cmds.pluginInfo('mtoa', query=True, loaded=True): return
        try:
            current_aov_nodes = cmds.ls(type='aiAOV')
            aov_map = {cmds.getAttr(f"{node}.name"): node for node in current_aov_nodes if cmds.attributeQuery("name", node=node, exists=True)}
            if not aov_map: return
            col_aov_root = layer.createCollection(f"COL_{layer.name()}_AOV_Settings")
            for aov_name, enabled in aov_settings.items():
                if aov_name in aov_map:
                    try:
                        col_single_aov = col_aov_root.createCollection(f"COL_AOV_{aov_name}")
                        col_single_aov.getSelector().setPattern(aov_map[aov_name])
                        enabled_override = col_single_aov.createAbsoluteOverride('aiAOV', 'enabled')
                        if enabled_override: enabled_override.setAttrValue(enabled)
                    except Exception as e: logging.warning(f"AOV '{aov_name}' のオーバーライド設定に失敗しました: {e}")
        except Exception as e: logging.error(f"AOVオーバーライドの適用中にエラーが発生しました: {e}")

    def _cleanup_failed_layer(self, layer):
        if not layer or not cmds.objExists(layer.name()): return
        logging.info(f"Cleanup: Removing partially created layer {layer.name()}.")
        try:
            # 削除はcmds.deleteで行う
            cmds.delete(layer.name())
        except Exception as e:
            logging.error(f"レイヤーのクリーンアップに失敗: {e}")

    # 【修正】レイヤー削除をcmds.delete()方式に戻す
    def delete_render_layer(self, layer_name):
        try:
            if cmds.objExists(layer_name):
                # デフォルトレイヤーでないことを確認
                if layer_name != "defaultRenderLayer":
                    cmds.delete(layer_name)
                    return True
            return False
        except Exception as e:
            logging.warning(f"レイヤー '{layer_name}' の削除中に予期せぬエラーが発生: {e}")
            return False

    def delete_multiple_layers(self, layer_names):
        count = 0
        for name in layer_names:
            if self.delete_render_layer(name):
                count += 1
        return count

    # 【修正】'.get()'メソッドが存在しないエラーを修正
    def get_layer_contents(self, layer_name):
        if not layer_name: return None
        layer = self.rs_instance.getRenderLayer(layer_name)
        if not layer: raise ValueError(f"Render layer '{layer_name}' not found.")
        contents = {"Target": [], "PVOff": [], "Visible": [], "WorldMatte": []}
        for col in layer.getCollections():
            key = None
            col_name = col.name()
            if "_Target" in col_name: key = "Target"
            elif "_PVOff" in col_name: key = "PVOff"
            elif "_Visible" in col_name: key = "Visible"
            elif "_WorldMatte" in col_name: key = "WorldMatte"
            if key:
                try:
                    # staticSelectionオブジェクトはイテレート可能なので直接リストに変換する
                    static_selection_list = list(col.getSelector().staticSelection)
                    if static_selection_list:
                        contents[key].extend(static_selection_list)
                except Exception as e:
                    logging.warning(f"Could not get members from collection {col_name}: {e}")
        return {k: sorted(list(set(v))) for k, v in contents.items() if v}