# -*- coding: utf-8 -*-
# render_layer_tool/aov.py
from __future__ import annotations
import maya.cmds as cmds
# --- 修正: 相対インポートから直接インポートに変更 ---
from rs_utils import logger, _ensure_mtoa_loaded

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
            plug = aov_if.getAOVNode(internal)
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
    # この関数は現在、直接は呼び出されていないため、実装は省略されています。
    # 必要に応じて visibility.py の safe_create_override をインポートして使用してください。
    # from rs_utils import safe_create_override
    logger.debug("setup_aov_collections is not fully implemented.")
    pass

