# -*- coding: utf-8 -*-
# render_layer_tool/visibility.py
from __future__ import annotations
import maya.cmds as cmds
# --- 修正: 相対インポートから直接インポートに変更 ---
from rs_utils import logger, safe_create_override, _clean_node_name_for_collection

try:
    from maya.app.renderSetup.model import selector as rs_selector
    RENDER_SETUP_API_AVAILABLE = True
except Exception:
    RENDER_SETUP_API_AVAILABLE = False
    rs_selector = None

def _choose_arnold_vis_attr(node: str) -> str | None:
    """Arnold 可視ビット属性名を環境差で吸収"""
    for cand in ("aiVisibility", "visibility"):
        try:
            if cmds.attributeQuery(cand, node=node, exists=True):
                return cand
        except Exception:
            pass
    return None

def create_collections_by_shapes(
    layer,
    parent_collection_name: str,
    shapes_to_process,
    action: str = "NONE",
):
    if not shapes_to_process:
        return None

    try:
        parent_col = layer.createCollection(parent_collection_name)
        if RENDER_SETUP_API_AVAILABLE and hasattr(parent_col.getSelector(), "setPattern"):
            parent_col.getSelector().setPattern("")
    except Exception as e:
        logger.error(f"Create parent collection failed: {e}")
        return None

    actions = {"ON": (255, 1, 1), "MATTE": (254, 0, 1), "HIDE": (0, 0, 0)}
    arnold_vis, maya_pv, xform_vis = actions.get(action, (None, None, None))
    prefix = {"ON": "TGT", "MATTE": "MAT", "HIDE": "HID", "NONE": "MBR"}.get(action, "MBR")

    for shape in shapes_to_process:
        if not cmds.objExists(shape):
            continue
        parents = cmds.listRelatives(shape, parent=True, fullPath=True)
        if not parents:
            continue
        xform = parents[0]
        
        try:
            sub_name = f"Col_{prefix}_{_clean_node_name_for_collection(shape)}"
            try:
                sub_col = parent_col.createCollection(sub_name)
            except RuntimeError:
                sub_col = parent_col.createCollection(f"{sub_name}_{len(cmds.ls(f'{sub_name}*', long=True)) + 1}")

            sel = sub_col.getSelector()
            if RENDER_SETUP_API_AVAILABLE and hasattr(sel, "staticSelection"):
                sel.staticSelection.set([xform, shape])
            elif RENDER_SETUP_API_AVAILABLE and hasattr(sel, "setPattern"):
                sel.setPattern(f"{xform},{shape}")
            
            if action != "NONE":
                if cmds.attributeQuery("primaryVisibility", node=shape, exists=True) and maya_pv is not None:
                    safe_create_override(sub_col, shape, "primaryVisibility", int(bool(maya_pv)))
                
                arnold_attr = _choose_arnold_vis_attr(shape)
                if arnold_attr and arnold_vis is not None:
                    safe_create_override(sub_col, shape, arnold_attr, int(arnold_vis))
                
                if xform_vis is not None:
                    safe_create_override(sub_col, xform, "visibility", int(bool(xform_vis)))
        except Exception as e:
            logger.error(f"[VIS] sub-collection failed for {shape}: {e}")
            
    return parent_col

