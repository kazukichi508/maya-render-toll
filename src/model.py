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
            
            if valid_targets:
                target_col = layer.createCollection(f"COL_{layer_name}_Target")
                target_col.getSelector().staticSelection.set(valid_targets)

            if valid_pvoffs:
                pvoff_col = layer.createCollection(f"COL_{layer_name}_PVOff")
                pvoff_col.getSelector().staticSelection.set(valid_pvoffs)
                # PVOffリストのオブジェクトに、手動操作を模倣したオーバーライドを適用
                self._apply_pv_off_override_by_shape(pvoff_col)
            
            self._setup_aov_overrides(layer, aov_settings)
            return True
        except Exception as e:
            log.error(f"レンダーレイヤー構造の作成中にエラーが発生しました ({layer_name}): {traceback.format_exc()}")
            if layer: self._cleanup_failed_layer(layer)
            return False

    def _apply_pv_off_override_by_shape(self, pvoff_collection):
        """
        手動操作を模倣し、コレクション内の各オブジェクトのシェイプに対して
        直接Absolute Overrideを作成する。
        """
        try:
            transform_nodes = list(pvoff_collection.getSelector().staticSelection)
            log.info(f"Applying PV OFF override to {len(transform_nodes)} objects in '{pvoff_collection.name()}'")

            for transform_node in transform_nodes:
                shapes = cmds.listRelatives(transform_node, shapes=True, fullPath=True, noIntermediate=True)
                if not shapes:
                    log.warning(f"Skipping '{transform_node}' as it has no renderable shape.")
                    continue

                for shape in shapes:
                    if not cmds.attributeQuery('primaryVisibility', node=shape, exists=True):
                        log.warning(f"Skipping '{shape}' as it has no 'primaryVisibility' attribute.")
                        continue
                    
                    log.info(f"  Creating AbsoluteOverride for '{shape}.primaryVisibility'")
                    abs_ovr = pvoff_collection.createAbsoluteOverride(shape, 'primaryVisibility')
                    
                    if abs_ovr:
                        try:
                            abs_ovr.setAttrValue(0) # 0 = OFF
                            log.info(f"    Successfully set override value to 0 for '{shape}'")
                        except Exception:
                            log.warning(f"    'setAttrValue' failed. Falling back to cmds.setAttr for '{shape}'")
                            # setAttrValueが失敗した場合の最終手段
                            override_node_name = abs_ovr.name()
                            attribute_plug = f"{override_node_name}.attrValue"
                            cmds.setAttr(attribute_plug, 0)
                            log.info(f"    Successfully set override value via cmds.setAttr for '{shape}'")
                    else:
                        log.error(f"    Failed to create AbsoluteOverride for '{shape}'")

        except Exception as e:
            log.error(f"PV OFF overrideの適用中に予期せぬエラー: {e} @ {pvoff_collection.name()}")
            traceback.print_exc()
            cmds.warning(f"PV OFF機能がコレクション '{pvoff_collection.name()}' で失敗しました。")

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