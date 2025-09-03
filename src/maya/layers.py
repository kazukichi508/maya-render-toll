# -*- coding: utf-8 -*-
# render_layer_tool/layers.py
from __future__ import annotations
import re
import maya.cmds as cmds

# 他の内部モジュールからのインポート
from .rs_utils import (
    logger, ensure_arnold_renderer, get_render_setup_instance, get_or_create_layer, 
    _safe_switch_to_master
)

# 作成ロジックに必要なインポート（仮定）
# from .scene_query import (...)
# from .visibility import (...)
# from .aov import (...)


# 【重要】Render Setupのレイヤー操作APIをインポート
RENDER_LAYER_API_AVAILABLE = False
renderLayer = None
try:
    # レイヤー削除に必要なモジュール。
    from maya.app.renderSetup.model import renderLayer
    RENDER_LAYER_API_AVAILABLE = True
except ImportError as e:
    logger.error(f"CRITICAL: Could not import renderLayer model API. Layer deletion will be disabled.", exc_info=True)


# ========== レイヤー作成ロジック ==========
# ※ここには前回提供した最新のレイヤー作成ロジックが入ります。
# ダミー関数（プレースホルダー）
def create_render_layer(*args, **kwargs): 
    logger.warning("create_render_layer is currently a dummy function. Please implement.")
    return False
def create_layers_for_each_solo_object(*args, **kwargs):
    logger.warning("create_layers_for_each_solo_object is currently a dummy function.")
    return 0, 0


# ========== レイヤー管理ロジック（削除機能） ==========

def get_all_render_layers() -> list[str]:
    rs = get_render_setup_instance()
    if not rs: return []
    try:
        return [layer.name() for layer in rs.getRenderLayers() if layer.name() != 'masterLayer' and layer.name() != 'defaultRenderLayer']
    except Exception as e:
        logger.error(f"Failed to get render layers: {e}", exc_info=True)
        return []

def delete_render_layers(layer_names_to_delete: list[str]) -> bool:
    """指定された名前のレンダーレイヤーを削除する。"""
    logger.info(f"[DIAG-Layers] delete_render_layers called with: {layer_names_to_delete}")
    rs = get_render_setup_instance()
    if not rs:
        logger.error("Render Setup instance not available.")
        return False
    
    if not RENDER_LAYER_API_AVAILABLE or renderLayer is None:
        logger.error("Render Layer API not available.")
        return False
        
    # 【重要】削除前にマスターレイヤーへ切り替え、結果を確認
    logger.debug("[DIAG-Layers] Switching to master layer before deletion.")
    if not _safe_switch_to_master(rs):
        # 切り替えに失敗した場合は処理を中断
        logger.error("[DIAG-Layers] Failed to switch to master layer. Aborting deletion.")
        return False
    
    success_count = 0
    
    # 削除処理
    for name in layer_names_to_delete:
        if name == 'masterLayer' or name == 'defaultRenderLayer': continue
        
        layer_obj = None
        try:
            # 対象のレイヤーオブジェクトを探す
            current_layers = rs.getRenderLayers()
            for layer in current_layers:
                if layer.name() == name:
                    layer_obj = layer
                    break
        except Exception as e:
            logger.error(f"Error while searching for layer '{name}': {e}", exc_info=True)
            continue
            
        if not layer_obj:
            logger.debug(f"[DIAG-Layers] Layer '{name}' not found. Skipping.")
            continue
        
        # 【再確認】削除対象レイヤーがアクティブでないことを確認
        try:
            if rs.getVisibleRenderLayer() == layer_obj:
                logger.error(f"[DIAG-Layers] CRITICAL: Layer '{name}' is still active. Cannot delete safely.")
                return False # 安全のため中断
        except Exception:
            pass

        try:
            logger.info(f"[DIAG-Layers] Executing renderLayer.delete() for: {name}")
            # 削除を実行
            renderLayer.delete(layer_obj)
            success_count += 1
            logger.info(f"[DIAG-Layers] Successfully deleted layer: {name}")

        except Exception as e:
            # 削除に失敗した場合、詳細ログを出力
            logger.error(f"[DIAG-Layers] FAILED to delete layer '{name}'.", exc_info=True)
            # 念のためマスターレイヤーに戻る試み
            _safe_switch_to_master(rs)

    logger.info(f"Deletion process finished. Success count: {success_count}/{len(layer_names_to_delete)}.")
    return success_count > 0

def delete_all_render_layers() -> bool:
    logger.debug("[DIAG-Layers] delete_all_render_layers called.")
    layers_to_delete = get_all_render_layers()
    if not layers_to_delete:
        logger.info("No render layers to delete.")
        return True
    return delete_render_layers(layers_to_delete)