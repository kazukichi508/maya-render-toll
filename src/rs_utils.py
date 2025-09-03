# -*- coding: utf-8 -*-
# render_layer_tool/rs_utils.py
from __future__ import annotations
import logging
import re
import time
import maya.cmds as cmds
import maya.mel as mel
import maya.utils as utils

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

logger = logging.getLogger("RenderLayerTool")
if not logger.handlers:
    logger.setLevel(logging.DEBUG)
    handler = logging.StreamHandler()
    formatter = logging.Formatter("[%(levelname)s] %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)


def _ensure_mtoa_loaded():
    if not cmds.pluginInfo("mtoa", q=True, loaded=True):
        try: cmds.loadPlugin("mtoa", quiet=True)
        except Exception: return False
    return True

def get_render_setup_instance():
    if renderSetup:
        try: return renderSetup.instance()
        except Exception as e:
            logger.error(f"Failed to get Render Setup instance: {e}")
    return None

def get_or_create_layer(rs_instance, layer_name):
    if not rs_instance: return None
    try:
        for layer in rs_instance.getRenderLayers():
            if layer.name() == layer_name:
                return layer
        return rs_instance.createRenderLayer(layer_name)
    except Exception as e:
        logger.error(f"Failed to get or create layer '{layer_name}': {e}")
        return None

def _safe_switch_to_master(rs_instance) -> bool:
    """
    マスターレイヤーへ安全に切り替える。UIの更新を考慮し、複数回リトライする。
    """
    logger.debug("[DIAG-Utils] Attempting robust switch to master layer...")
    if not rs_instance:
        logger.error("rs_instance is None.")
        return False

    try:
        master_layer = rs_instance.getDefaultRenderLayer()
        if not master_layer:
            logger.error("Master layer (defaultRenderLayer) not found.")
            return False

        for attempt in range(3):
            if rs_instance.getVisibleRenderLayer() == master_layer:
                logger.debug(f"Already on master layer. (Attempt {attempt + 1})")
                return True

            logger.info(f"Switching to '{master_layer.name()}'... (Attempt {attempt + 1})")
            rs_instance.switchToLayer(master_layer)
            
            utils.executeDeferred(cmds.evalDeferred)
            time.sleep(0.1 * (attempt + 1)) 

            if rs_instance.getVisibleRenderLayer() == master_layer:
                logger.debug("Switch successful.")
                return True
            else:
                logger.warning(f"Verification failed after attempt {attempt + 1}.")

        logger.error("Failed to switch to master layer after multiple attempts.")
        return False

    except Exception as e:
        logger.error(f"An unexpected error occurred in _safe_switch_to_master: {e}", exc_info=True)
        return False

def _clean_node_name_for_collection(node_path):
    return re.sub(r'[:|]', '_', node_path.lstrip('|'))

# --- ▼▼▼【修正点】不足していた関数を追加 ▼▼▼ ---
def safe_create_override(collection, node, attr, value):
    """
    AbsoluteOverrideを安全に作成し、値を設定する。
    Mayaのバージョン差異を吸収するため、複数の方法を試行する。
    """
    if not RENDER_SETUP_API_AVAILABLE or not rs_override:
        logger.error("safe_create_override: Render Setup API not available.")
        return None
    
    if not cmds.objExists(node) or not cmds.attributeQuery(attr, node=node, exists=True):
        logger.warning(f"Attribute not found, skipping override: {node}.{attr}")
        return None

    node_attr = f"{node}.{attr}"

    try:
        # Maya 2019以降で推奨される方法 (node, attr)
        override = collection.createAbsoluteOverride(node, attr)
        override.setAttrValue(value)
        logger.debug(f"Created override (2-arg): {node_attr} = {value}")
        return override
    except TypeError:
        # 古いバージョンとの互換性のためのフォールバック
        try:
            # Maya 2017-2018 での標準的な方法 ("node.attr")
            override = collection.createAbsoluteOverride(node_attr)
            override.setAttrValue(value)
            logger.debug(f"Created override (1-arg): {node_attr} = {value}")
            return override
        except Exception as e:
            logger.error(f"Failed to create override for {node_attr}: {e}", exc_info=True)
            return None
    except Exception as e:
        logger.error(f"An unexpected error occurred in safe_create_override for {node_attr}: {e}", exc_info=True)
        return None
# --- ▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲ ---

