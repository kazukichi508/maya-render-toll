# -*- coding: utf-8 -*-
# render_layer_tool/aov.py
from __future__ import annotations
import maya.cmds as cmds
from rs_utils import logger, _ensure_mtoa_loaded, safe_create_override

AOV_NAME_MAP = {
    "diffuse": "diffuse", "specular": "specular", "coat": "coat",
    "transmission": "transmission", "sss": "sss", "volume": "volume",
    "emission": "emission", "background": "background", "id": "id",
    "shadow_matte": "shadow_matte", "N": "N", "P": "P", "AO": "ambient_occlusion",
}

def ensure_aovs_exist(aov_ui_names):
    """指定 UI 名の AOV を作成/取得し、aiAOV_* ノード名のリストを返す"""
    _ensure_mtoa_loaded()
    try:
        import mtoa.aovs as aovs
        aov_if = aovs.AOVInterface()
    except Exception:
        logger.warning("Could not import mtoa.aovs. Skipping AOV setup.")
        return []
    nodes = []
    for ui in aov_ui_names or []:
        internal = AOV_NAME_MAP.get(ui)
        if not internal: continue
        plug = aov_if.getAOVNode(internal)
        if not plug:
            try:
                aov_if.addAOV(internal)
                plug = aov_if.getAOVNode(internal)
                logger.debug(f"[AOV] created: {internal}")
            except Exception as e:
                cmds.warning(f"[AOV] create failed: {internal} ({e})")
                continue
        if plug:
            node = str(plug).split(".", 1)[0]
            if cmds.objExists(node):
                nodes.append(node)
    return nodes

def setup_aov_overrides(layer, layer_name: str, aov_settings: dict | None):
    """AOV 有効/無効のレイヤーオーバーライドを構築"""
    if not aov_settings: return

    aovs_to_enable_ui = [name for name, enabled in aov_settings.items() if enabled]
    if not aovs_to_enable_ui:
        logger.debug("No AOVs selected to enable.")
        return
        
    aov_nodes = ensure_aovs_exist(aovs_to_enable_ui)
    if not aov_nodes:
        logger.warning("No valid AOV nodes found to create overrides for.")
        return
        
    aov_col = layer.createCollection(f"{layer_name}_AOV")
    
    for node in aov_nodes:
        if cmds.attributeQuery("enabled", node=node, exists=True):
            safe_create_override(aov_col, node, "enabled", True)
        else:
            logger.warning(f"Attribute 'enabled' not found on node {node}. Skipping override.")