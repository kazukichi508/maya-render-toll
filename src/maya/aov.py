# -*- coding: utf-8 -*-
# render_layer_tool/aov.py
from __future__ import annotations
import maya.cmds as cmds
from .rs_utils import logger, _ensure_mtoa_loaded, safe_create_override

# AOV UI名 → 内部名
AOV_NAME_MAP = {
    "diffuse": "diffuse",
    "specular": "specular",
    "coat": "coat",
    "transmission": "transmission",
    "sss": "sss",
    "volume": "volume",
    "emission": "emission",
    "background": "background",
    "id": "id",
    "shadow_matte": "shadow_matte",
    "N": "N",
    "P": "P",
    "AO": "ambient_occlusion",
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
        if not internal:
            continue

        plug = None
        try:
            plug = aov_if.getAOVNode(internal)  # 'aiAOV_xxx.message'
        except Exception:
            plug = None

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

def setup_aov_collections(layer, layer_name: str, aov_settings: dict | None):
    """AOV 有効/無効のレイヤーオーバーライドを構築"""
    try:
        all_aovs = cmds.ls(type="aiAOV") or []
        if all_aovs:
            try:
                disable_col = layer.createCollection(f"{layer_name}_AOVs_DISABLE_ALL")
                if hasattr(disable_col.getSelector(), "setPattern"):
                    disable_col.getSelector().setPattern("aiAOV_*")
                # 代表ノードで enabled=False の絶対オーバーライドを作成
                safe_create_override(disable_col, all_aovs[0], "enabled", False)
            except Exception as e:
                logger.error(f"AOV DISABLE collection failed: {e}")

        enabled_ui = [n for n, checked in (aov_settings or {}).items() if checked]
        if enabled_ui:
            nodes_to_enable = ensure_aovs_exist(enabled_ui)
            if nodes_to_enable:
                try:
                    enable_col = layer.createCollection(f"{layer_name}_AOVs_ENABLE_SELECTED")
                    if hasattr(enable_col.getSelector(), "staticSelection"):
                        enable_col.getSelector().staticSelection.add(nodes_to_enable)
                    for n in nodes_to_enable:
                        safe_create_override(enable_col, n, "enabled", True)
                except Exception as e:
                    logger.error(f"AOV ENABLE collection failed: {e}")
    except Exception as e:
        logger.warning(f"AOV setup skipped due to error: {e}")
