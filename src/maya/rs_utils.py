# -*- coding: utf-8 -*-
# render_layer_tool/rs_utils.py
from __future__ import annotations
import logging
import re
import maya.cmds as cmds
import maya.mel as mel

# Render Setup APIのインポート
RENDER_SETUP_API_AVAILABLE = False
renderSetup = None
rs_override = None
rs_selector = None

try:
    from maya.app.renderSetup.model import renderSetup
    from maya.app.renderSetup.model import override as rs_override
    from maya.app.renderSetup.model import selector as rs_selector
    RENDER_SETUP_API_AVAILABLE = True
except ImportError:
    logging.warning("Render Setup API not fully available.")

# ========== ロガー設定（ここで集約） ==========
logger = logging.getLogger("RenderLayerTool")
# ハンドラの重複防止
if not logger.handlers:
    logger.setLevel(logging.DEBUG)
    handler = logging.StreamHandler()
    formatter = logging.Formatter("[%(levelname)s] %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)


# ========== 基本ヘルパー ==========

def _ensure_mtoa_loaded():
    if not cmds.pluginInfo("mtoa", q=True, loaded=True):
        try:
            cmds.loadPlugin("mtoa", quiet=True)
            return True
        except Exception:
            return False
    return True

def ensure_arnold_renderer():
    _ensure_mtoa_loaded()
    if cmds.getAttr("defaultRenderGlobals.currentRenderer") != "arnold":
        cmds.setAttr("defaultRenderGlobals.currentRenderer", "arnold", type="string")
    # (省略: Arnold詳細設定)

def get_render_setup_instance():
    if renderSetup:
        try:
            return renderSetup.instance()
        except Exception as e:
            logger.error(f"Failed to get Render Setup instance: {e}")
            return None
    return None

def get_or_create_layer(rs_instance, layer_name):
    try:
        all_layers = rs_instance.getRenderLayers()
        for layer in all_layers:
            if layer.name() == layer_name:
                return layer
    except Exception:
        pass
    try:
        layer = rs_instance.createRenderLayer(layer_name)
        return layer
    except Exception as e:
        logger.error(f"Failed to create render layer '{layer_name}': {e}")
        return None

# --- 【重要】マスターレイヤーへの切り替えヘルパー (堅牢版) ---
def _safe_switch_to_master(rs_instance) -> bool:
    """
    マスターレイヤーへ安全に切り替える。成功したらTrue、失敗したらFalseを返す。
    """
    logger.debug("[DIAG-Utils] Attempting safe switch to master layer...")
    if not rs_instance:
         logger.error("rs_instance is None.")
         return False

    try:
        master_layer = None
        try:
            all_layers = rs_instance.getRenderLayers()
        except Exception as e:
            logger.error(f"Failed to get render layers list: {e}", exc_info=True)
            return False

        # マスターレイヤーを探す
        for layer in all_layers:
            if layer.name() == 'masterLayer' or layer.name() == 'defaultRenderLayer':
                master_layer = layer
                break
        
        if not master_layer:
            logger.error("Master layer not found.")
            return False

        # 現在の表示レイヤーを取得
        try:
            current_visible_layer = rs_instance.getVisibleRenderLayer()
        except Exception:
            current_visible_layer = None

        # 切り替えを実行
        if current_visible_layer != master_layer:
            try:
                logger.info(f"[DIAG-Utils] Switching from '{getattr(current_visible_layer, 'name()', 'Unknown')}' to '{master_layer.name()}'.")
                rs_instance.switchToLayer(master_layer)
                
                # 【重要】切り替え後の再確認 (Verify)
                if rs_instance.getVisibleRenderLayer() == master_layer:
                    logger.debug("[DIAG-Utils] Switch successful.")
                    return True
                else:
                    logger.error("[DIAG-Utils] Switch command executed, but verification failed. Still not on master layer.")
                    return False

            except Exception as e:
                logger.error(f"Failed to execute switch command to master layer: {e}", exc_info=True)
                return False
        else:
            logger.debug("[DIAG-Utils] Already on master layer.")
            return True

    except Exception as e:
        logger.error(f"An unexpected error occurred in _safe_switch_to_master: {e}", exc_info=True)
        return False

def _clean_node_name_for_collection(node_path):
    return re.sub(r'[:|]', '_', node_path.lstrip('|'))