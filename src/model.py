# render_layer_tool/model.py
# -*- coding: utf-8 -*-
"""
データ処理とMayaのシーン操作を担当するModel層。
"""
import maya.cmds as cmds
from maya.app.renderSetup.model import renderSetup, renderLayer, override, selector

class RenderLayerModel:
    """
    ツールのコアロジックを管理するクラス。
    """
    def __init__(self):
        try:
            self.rs = renderSetup.instance()
        except Exception as e:
            raise RuntimeError(f"Render Setupの初期化に失敗しました: {e}")

    # --- レイヤー操作 ---
    
    def get_all_layers(self) -> list[str]:
        layers = self.rs.getRenderLayers()
        return [lyr.name() for lyr in layers if lyr.name() not in ('masterLayer', 'defaultRenderLayer')]

    def create_layer(self, layer_name: str, targets: list[str], pv_off: list[str]) -> bool:
        if not layer_name:
            cmds.warning("レイヤー名が指定されていません。")
            return False
            
        layer = self.rs.getRenderLayer(layer_name) or self.rs.createRenderLayer(layer_name)

        if targets:
            target_col = layer.createCollection(f"{layer_name}_TARGETS")
            target_col.getSelector().setStaticSelection(targets)
            ov = target_col.createAbsoluteOverride(targets[0], 'primaryVisibility')
            ov.setAttrValue(True)

        if pv_off:
            pv_off_col = layer.createCollection(f"{layer_name}_MATTES")
            pv_off_col.getSelector().setStaticSelection(pv_off)
            ov = pv_off_col.createAbsoluteOverride(pv_off[0], 'primaryVisibility')
            ov.setAttrValue(False)
            
        return True

    def delete_layers(self, layer_names: list[str]) -> bool:
        if not layer_names:
            return False
        self._safe_switch_to_master()
        for name in layer_names:
            layer_to_delete = self.rs.getRenderLayer(name)
            if layer_to_delete:
                renderLayer.delete(layer_to_delete)
        return True

    def delete_all_layers(self) -> bool:
        all_layers = self.get_all_layers()
        return self.delete_layers(all_layers)

    def _safe_switch_to_master(self):
        master_layer = self.rs.getRenderLayer('masterLayer')
        if self.rs.getVisibleRenderLayer() != master_layer:
            self.rs.switchToLayer(master_layer)

    # --- シーン情報 ---

    def get_selection(self) -> list[str]:
        return cmds.ls(sl=True, long=True) or []

    def get_scene_hierarchy(self) -> dict:
        hierarchy = {}
        for root in cmds.ls(assemblies=True, long=True):
            # --- ★★ここを修正★★ ---
            # カメラ以外のオブジェクトでエラーが出ないようにtry...exceptで囲む
            try:
                if cmds.camera(root, q=True, startupCamera=True):
                    continue
            except RuntimeError:
                # オブジェクトがカメラでない場合にこのエラーが発生するが、
                # 処理を続行して問題ないため、passで無視する
                pass
            # -------------------------
            
            hierarchy[root] = self._build_hierarchy_recursive(root)
        return hierarchy

    def _build_hierarchy_recursive(self, node: str) -> dict:
        node_info = {'type': 'group', 'primaryVisibility': None, 'children': {}}
        shapes = cmds.listRelatives(node, shapes=True, noIntermediate=True, fullPath=True)
        if shapes:
            shape = shapes[0]
            node_type = cmds.nodeType(shape)
            if 'mesh' in node_type:
                node_info['type'] = 'geometry'
                if cmds.attributeQuery('primaryVisibility', node=shape, exists=True):
                    node_info['primaryVisibility'] = cmds.getAttr(f"{shape}.primaryVisibility")
            elif 'camera' in cmds.nodeType(shape, inherited=True):
                node_info['type'] = 'camera'
            elif 'light' in cmds.nodeType(shape, inherited=True):
                node_info['type'] = 'light'

        children = cmds.listRelatives(node, children=True, type='transform', fullPath=True) or []
        for child in children:
            node_info['children'][child] = self._build_hierarchy_recursive(child)
            
        return node_info