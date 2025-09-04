# -*- coding: utf-8 -*-
# render_layer_tool/rs_utils.py
from __future__ import annotations
import logging
import re
import maya.cmds as cmds
import maya.utils as utils
import time

RENDER_SETUP_API_AVAILABLE = False
renderSetup = None
try:
    from maya.app.renderSetup.model import renderSetup
    RENDER_SETUP_API_AVAILABLE = True
except ImportError:
    logging.warning("Render Setup API not available.")

logger = logging.getLogger("RenderLayerTool")
if not logger.handlers:
    logger.setLevel(logging.DEBUG)
    handler = logging.StreamHandler()
    formatter = logging.Formatter("[%(levelname)s][%(module)s] %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)

def _ensure_mtoa_loaded():
    if not cmds.pluginInfo("mtoa", q=True, loaded=True):
        try:
            cmds.loadPlugin("mtoa", quiet=True)
            return True
        except Exception: return False
    return True

def ensure_arnold_renderer():
    _ensure_mtoa_loaded()
    if cmds.getAttr("defaultRenderGlobals.currentRenderer") != "arnold":
        try:
            cmds.setAttr("defaultRenderGlobals.currentRenderer", "arnold", type="string")
        except Exception as e:
            logger.error(f"Failed to set Arnold as renderer: {e}")

def get_render_setup_instance():
    if renderSetup:
        try: return renderSetup.instance()
        except Exception as e:
            logger.error(f"Failed to get Render Setup instance: {e}")
    return None

def get_or_create_layer(rs_instance, layer_name):
    try:
        for layer in rs_instance.getRenderLayers():
            if layer.name() == layer_name:
                return layer
        return rs_instance.createRenderLayer(layer_name)
    except Exception as e:
        logger.error(f"Failed to get/create layer '{layer_name}': {e}")
        return None

def _safe_switch_to_master(rs_instance) -> bool:
    if not rs_instance: return False
    try:
        master_layer = rs_instance.getDefaultRenderLayer()
        if not master_layer: return False
        for attempt in range(3):
            if rs_instance.getVisibleRenderLayer() == master_layer: return True
            rs_instance.switchToLayer(master_layer)
            utils.executeDeferred(cmds.evalDeferred)
            time.sleep(0.1 * (attempt + 1))
            if rs_instance.getVisibleRenderLayer() == master_layer: return True
        logger.error("Failed to switch to master layer.")
        return False
    except Exception as e:
        logger.error(f"Error in _safe_switch_to_master: {e}", exc_info=True)
        return False

def _clean_node_name_for_collection(node_path):
    return re.sub(r'[:|]', '_', node_path.lstrip('|'))

def safe_create_override(collection, node_name, attr_name, attr_value):
    try:
        override = collection.createAbsoluteOverride(node_name, attr_name)
        if override:
            override.setAttrValue(attr_value)
            return override
    except Exception as e:
        logger.warning(f"Failed to create override for {node_name}.{attr_name}: {e}")
    return None

