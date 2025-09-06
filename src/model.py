# -*- coding: utf-8 -*-
# render_layer_tool/model.py
"""
Model層のファサード（Facade）。
各専門モジュール（scene_query, layersなど）の機能を仲介する。
"""
import maya.cmds as cmds

# Render Setup APIが利用可能かどうかのチェック
RENDER_SETUP_API_AVAILABLE = False
renderSetup = None  # 変数を事前に定義
try:
    # このモジュールがインポートできればAPIは利用可能と判断
    from maya.app.renderSetup.model import renderSetup
    RENDER_SETUP_API_AVAILABLE = True
except ImportError:
    # インポートに失敗した場合、APIは利用不可
    pass


# --- scene_query.py からの機能 ---
import scene_query
def get_raw_selection():
    """scene_queryのget_raw_selectionを公開する。"""
    return scene_query.get_raw_selection()

def get_categorized_scene_hierarchy():
    """scene_queryのget_categorized_scene_hierarchyを公開する。"""
    return scene_query.get_categorized_scene_hierarchy()

def get_renderable_descendants(root_node):
    """scene_queryのget_renderable_descendantsを公開する。"""
    return scene_query.get_renderable_descendants(root_node)


# --- layers.py からの機能 (再実装) ---

def create_render_layer(layer_name, target_objects):
    """
    layers.pyの代替機能。
    指定された名前でレンダーレイヤーを作成し、対象オブジェクトをコレクションに追加する。
    """
    if not RENDER_SETUP_API_AVAILABLE:
        cmds.warning("Render Setup is not available in this version of Maya.")
        return False

    try:
        rs = renderSetup.instance()
        
        layer = rs.getRenderLayer(layer_name)
        if not layer:
            layer = rs.createRenderLayer(layer_name)
        
        for collection in layer.getCollections():
            cmds.delete(collection.name())
            
        if not target_objects:
            return True

        collection = layer.createCollection("render_targets")
        pattern = " ".join(target_objects)
        collection.getSelector().setPattern(pattern)
        
        return True
    except Exception as e:
        cmds.warning(f"Failed to create/update render layer '{layer_name}': {e}")
        return False

def get_all_render_layers():
    """
    layers.pyの代替機能。
    シーン内の全てのレンダーレイヤー名（defaultRenderLayerを除く）を返す。
    """
    if not RENDER_SETUP_API_AVAILABLE:
        return []
    try:
        rs = renderSetup.instance()
        layers = rs.getRenderLayers()
        return [layer.name() for layer in layers if layer.name() != "defaultRenderLayer"]
    except Exception:
        return []

def delete_render_layers(layer_names_to_delete):
    """
    layers.pyの代替機能。
    指定された名前のレンダーレイヤーを削除する。
    """
    if not RENDER_SETUP_API_AVAILABLE:
        cmds.warning("Render Setup is not available to delete layers.")
        return False
    
    if not layer_names_to_delete:
        return True

    try:
        # 削除前に存在するレイヤー名のみをリストアップ
        existing_layers = [name for name in layer_names_to_delete if cmds.objExists(name)]
        
        if not existing_layers:
            # 削除対象が存在しない場合も成功とする
            return True
            
        # Mayaの標準コマンドを使ってレイヤーノードを直接削除
        cmds.delete(existing_layers)
        return True
    except Exception as e:
        cmds.warning(f"Failed to delete render layers: {e}")
        return False

def delete_all_render_layers():
    """
    layers.pyの代替機能。
    全てのレンダーレイヤー（defaultRenderLayerを除く）を削除する。
    """
    try:
        all_layers = get_all_render_layers()
        if all_layers:
            return delete_render_layers(all_layers)
        return True
    except Exception:
        return False

