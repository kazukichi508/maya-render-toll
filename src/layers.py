# -*- coding: utf-8 -*-
# render_layer_tool/layers.py
from __future__ import annotations
import maya.cmds as cmds

# 関連モジュールをインポート
import rs_utils
import scene_query

RENDER_LAYER_API_AVAILABLE = False
renderLayer = None
try:
    from maya.app.renderSetup.model import renderLayer
    RENDER_LAYER_API_AVAILABLE = True
except ImportError:
    rs_utils.logger.error("CRITICAL: Could not import renderLayer model API.", exc_info=True)


def create_render_layer(layer_name, target_objects):
    """
    指定された名前でレンダーレイヤーを作成し、
    単一のコレクションに選択されたすべてのオブジェクトを追加する。
    """
    rs_utils.logger.info(f"--- Creating layer '{layer_name}' with a single collection ---")
    if not layer_name:
        rs_utils.logger.error("Layer name is required.")
        return False
    if not target_objects:
        rs_utils.logger.warning("No target objects provided for layer creation.")
        return False

    rs = rs_utils.get_render_setup_instance()
    if not rs: return False
    rs_utils.ensure_arnold_renderer()

    try:
        # レイヤーを取得または作成
        layer = rs_utils.get_or_create_layer(rs, layer_name)
        if not layer: return False

        # 既存のコレクションを一度すべてクリア
        for col in reversed(list(layer.getCollections())):
            try:
                layer.removeCollection(col)
            except Exception as e:
                rs_utils.logger.warning(f"Failed to remove existing collection {col.name()}: {e}")

        # コレクションを1つだけ作成
        collection = layer.createCollection(f"{layer_name}_col")
        
        # ターゲットオブジェクトとそのシェイプノードを取得
        shapes = scene_query.get_shapes_from_transforms(target_objects)
        all_members_to_add = sorted(list(set(target_objects + shapes)))
        
        # 取得したすべてのメンバーを単一のコレクションに設定
        collection.getSelector().setStaticSelection(all_members_to_add)

        rs.switchToLayer(layer)
        rs_utils.logger.info(f"--- Successfully created/updated layer '{layer_name}' ---")
        return True
    except Exception as e:
        rs_utils.logger.error(f"An exception occurred during layer creation: {e}", exc_info=True)
        try:
            rs_utils._safe_switch_to_master(rs)
        except Exception: pass
        return False


def get_all_render_layers() -> list[str]:
    """マスターレイヤー以外のすべてのレンダーレイヤー名を取得する。"""
    rs = rs_utils.get_render_setup_instance()
    if not rs: return []
    try:
        default_layer = rs.getDefaultRenderLayer()
        return [layer.name() for layer in rs.getRenderLayers() if layer != default_layer]
    except Exception as e:
        rs_utils.logger.error(f"Failed to get render layers: {e}", exc_info=True)
        return []

def delete_render_layers(layer_names_to_delete: list[str]) -> bool:
    """指定された名前のレンダーレイヤーを削除する。"""
    rs = rs_utils.get_render_setup_instance()
    if not rs or not RENDER_LAYER_API_AVAILABLE:
        return False
        
    if not rs_utils._safe_switch_to_master(rs):
        rs_utils.logger.error("Failed to switch to master layer. Aborting deletion.")
        return False
    
    success_count = 0
    default_layer = rs.getDefaultRenderLayer()
    for name in layer_names_to_delete:
        try:
            layer_obj = rs.getRenderLayer(name)
            if layer_obj and layer_obj != default_layer:
                renderLayer.delete(layer_obj)
                success_count += 1
                rs_utils.logger.info(f"Successfully deleted layer: {name}")
        except Exception:
            rs_utils.logger.error(f"FAILED to delete layer '{name}'.", exc_info=True)
            
    return success_count > 0

def delete_all_render_layers() -> bool:
    layers_to_delete = get_all_render_layers()
    if not layers_to_delete:
        rs_utils.logger.info("No render layers to delete.")
        return True
    return delete_render_layers(layers_to_delete)