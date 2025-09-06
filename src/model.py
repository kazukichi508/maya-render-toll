# render_layer_tool/model.py
# -*- coding: utf-8 -*-
import maya.cmds as cmds
import logging
import traceback
import re

logging.basicConfig()
log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

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

    def reset(self):
        """Render Setupインスタンスへの参照を再取得して、内部状態をリフレッシュする。"""
        self.rs_instance = rs.instance()
        log.info("RenderLayerManager state has been reset.")

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

    def create_layers_from_lists(self, base_name, target_list, pvoff_list, settings):
        """
        TargetリストとPVOffリストから、それぞれ独立したレンダーレイヤーを作成する。
        """
        create_each = settings.get('create_each', False)
        
        layers_to_create_info = []

        # --- Target レイヤーの作成ジョブを生成 ---
        if target_list:
            if create_each:
                for obj in target_list:
                    layer_name = self._sanitize_name(obj)
                    layers_to_create_info.append({'name': layer_name, 'targets': [obj], 'pvoffs': pvoff_list})
            else:
                layer_name = self._sanitize_name(base_name or target_list[0])
                layers_to_create_info.append({'name': layer_name, 'targets': target_list, 'pvoffs': pvoff_list})
        
        # --- PVOff レイヤーの作成ジョブを生成 ---
        # 【バグ修正】Targetリストの状態に関わらず、PVOffリストに項目があれば常に実行する
        if pvoff_list:
            layer_name = self._sanitize_name((base_name or "Scene") + "_PVOff")
            layers_to_create_info.append({'name': layer_name, 'targets': target_list, 'pvoffs': pvoff_list})

        if not layers_to_create_info:
            return 0

        # --- 生成されたジョブリストを元にレイヤーを実際に作成 ---
        existing_layer_names = set(self.list_render_layers())
        created_count = 0
        try:
            if rsInternal:
                with rsInternal.deferredEvaluation(True):
                    created_count = self._execute_layer_creation(layers_to_create_info, existing_layer_names, settings)
            else:
                created_count = self._execute_layer_creation(layers_to_create_info, existing_layer_names, settings)
        except Exception as e:
            log.error(f"レイヤー作成バッチ処理中にエラーが発生しました: {e}")
            raise
        return created_count

    def _execute_layer_creation(self, layers_to_create_info, existing_layer_names, settings):
        created_count = 0
        for layer_info in layers_to_create_info:
            layer_name_base = layer_info['name']
            targets = layer_info['targets']
            pvoffs = layer_info['pvoffs']
            
            final_layer_name = layer_name_base
            counter = 1
            while final_layer_name in existing_layer_names or cmds.objExists(final_layer_name):
                 final_layer_name = f"{layer_name_base}_{counter}"
                 counter += 1
            
            if self._create_single_layer_structure(final_layer_name, targets, pvoffs, settings):
                created_count += 1
                existing_layer_names.add(final_layer_name)
        return created_count

    def _create_single_layer_structure(self, layer_name, target_objects, pvoff_objects, settings):
        aov_settings = settings.get('aov_settings', {})
        layer = None
        try:
            layer = self.rs_instance.createRenderLayer(layer_name)
            if not layer: raise RuntimeError(f"Render Layer object creation returned None for {layer_name}")

            default_layer = self.rs_instance.getDefaultRenderLayer()
            if layer == default_layer:
                log.error(f"Attempted to create overrides on the default render layer. Aborting for '{layer_name}'.")
                return False

            valid_targets = [obj for obj in target_objects if cmds.objExists(obj)]
            valid_pvoffs = [obj for obj in pvoff_objects if cmds.objExists(obj)]
            
            is_pvoff_layer = "_PVOff" in layer_name

            if valid_targets:
                target_col = layer.createCollection(f"COL_{layer_name}_Target")
                target_col.getSelector().staticSelection.set(valid_targets)
                target_enabled = False if is_pvoff_layer else True
                self._apply_pv_override_by_shape(target_col, enabled=target_enabled)

            if valid_pvoffs:
                pvoff_col = layer.createCollection(f"COL_{layer_name}_PVOff")
                pvoff_col.getSelector().staticSelection.set(valid_pvoffs)
                pvoff_enabled = True if is_pvoff_layer else False
                self._apply_pv_override_by_shape(pvoff_col, enabled=pvoff_enabled)
            
            self._setup_aov_overrides(layer, aov_settings)
            return True
        except Exception as e:
            log.error(f"レンダーレイヤー構造の作成中にエラーが発生しました ({layer_name}): {traceback.format_exc()}")
            if layer: self._cleanup_failed_layer(layer)
            return False

    def _apply_pv_override_by_shape(self, collection, enabled=True):
        try:
            transform_nodes = list(collection.getSelector().staticSelection)
            status = "ON" if enabled else "OFF"
            log.info(f"Applying PV {status} override to {len(transform_nodes)} objects in '{collection.name()}'")

            for transform_node in transform_nodes:
                shapes = cmds.listRelatives(transform_node, shapes=True, fullPath=True, noIntermediate=True)
                if not shapes:
                    log.warning(f"Skipping '{transform_node}' as it has no renderable shape.")
                    continue

                for shape in shapes:
                    if not cmds.attributeQuery('primaryVisibility', node=shape, exists=True):
                        log.warning(f"Skipping '{shape}' as it has no 'primaryVisibility' attribute.")
                        continue
                    
                    abs_ovr = collection.createAbsoluteOverride(shape, 'primaryVisibility')
                    if abs_ovr:
                        try:
                            value = 1 if enabled else 0
                            abs_ovr.setAttrValue(value)
                        except Exception:
                            override_node_name = abs_ovr.name()
                            attribute_plug = f"{override_node_name}.attrValue"
                            cmds.setAttr(attribute_plug, value)
                    else:
                        log.error(f"    Failed to create AbsoluteOverride for '{shape}'")
        except Exception as e:
            log.error(f"PV overrideの適用中に予期せぬエラー: {e} @ {collection.name()}")
            traceback.print_exc()
            cmds.warning(f"PV機能がコレクション '{collection.name()}' で失敗しました。")

    def _setup_aov_overrides(self, layer, aov_settings):
        # (変更なし)
        pass

    def _cleanup_failed_layer(self, layer):
        if not layer or not cmds.objExists(layer.name()): return
        try:
            if layer != self.rs_instance.getDefaultRenderLayer():
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
        # (変更なし)
        if not layer_name: return None
        layer = self.rs_instance.getRenderLayer(layer_name)
        if not layer: raise ValueError(f"Render layer '{layer_name}' not found.")
        contents = {"Target": [], "PVOff": []}
        for col in layer.getCollections():
            key, col_name = None, col.name()
            if "_Target" in col_name: key = "Target"
            elif "_PVOff" in col_name: key = "PVOff"
            if key:
                try:
                    static_selection_list = list(col.getSelector().staticSelection)
                    if static_selection_list: contents[key].extend(static_selection_list)
                except Exception as e:
                    log.warning(f"Could not get members from collection {col_name}: {e}")
        return {k: sorted(list(set(v))) for k, v in contents.items() if v}