# -*- coding: utf-8 -*-
# render_layer_tool/layers.py
from __future__ import annotations
import maya.cmds as cmds

# --- 修正: 相対インポートから直接インポートに変更 ---
from rs_utils import (
    logger, get_render_setup_instance, _safe_switch_to_master
)

RENDER_LAYER_API_AVAILABLE = False
renderLayer = None
try:
    from maya.app.renderSetup.model import renderLayer
    RENDER_LAYER_API_AVAILABLE = True
except ImportError:
    logger.error("CRITICAL: Could not import renderLayer model API.", exc_info=True)

# (ダミー関数)
def create_render_layer(*args, **kwargs): return False
def create_layers_for_each_solo_object(*args, **kwargs): return 0, 0

def get_all_render_layers() -> list[str]:
    rs = get_render_setup_instance()
    if not rs: return []
    try:
        # isDefaultLayer() を使ってマスターレイヤーを除外する
        return [layer.name() for layer in rs.getRenderLayers() if not layer.isDefaultLayer()]
    except Exception as e:
        logger.error(f"Failed to get render layers: {e}", exc_info=True)
        return []

def delete_render_layers(layer_names_to_delete: list[str]) -> bool:
    rs = get_render_setup_instance()
    if not rs or not RENDER_LAYER_API_AVAILABLE:
        return False
        
    if not _safe_switch_to_master(rs):
        logger.error("Failed to switch to master layer. Aborting deletion.")
        return False
    
    success_count = 0
    for name in layer_names_to_delete:
        try:
            layer_obj = rs.getRenderLayer(name)
            if layer_obj and not layer_obj.isDefaultLayer():
                renderLayer.delete(layer_obj)
                success_count += 1
                logger.info(f"Successfully deleted layer: {name}")
        except Exception:
            logger.error(f"FAILED to delete layer '{name}'.", exc_info=True)
            
    logger.info(f"Deletion process finished. Success count: {success_count}/{len(layer_names_to_delete)}.")
    return success_count > 0

def delete_all_render_layers() -> bool:
    layers_to_delete = get_all_render_layers()
    if not layers_to_delete:
        logger.info("No render layers to delete.")
        return True
    return delete_render_layers(layers_to_delete)

