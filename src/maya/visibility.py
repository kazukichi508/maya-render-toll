# -*- coding: utf-8 -*-
# render_layer_tool/visibility.py
from __future__ import annotations
import maya.cmds as cmds
from .rs_utils import logger, safe_create_override, _clean_node_name_for_collection

# Render Setup selector
try:
    from maya.app.renderSetup.model import selector as rs_selector
    RENDER_SETUP_API_AVAILABLE = True
except Exception:
    RENDER_SETUP_API_AVAILABLE = False
    rs_selector = None  # type: ignore

def _choose_arnold_vis_attr(node: str) -> str | None:
    """Arnold 可視ビット属性名を環境差で吸収（'aiVisibility' 優先、無ければ 'visibility'）"""
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
    action: str = "NONE",  # 'ON'|'MATTE'|'HIDE'|'NONE'
):
    """
    shape 単位でサブコレクションを作成し、Arnold/Maya の Visibility をオーバーライド。
      - 'ON'   : Arnold=255, PV=1, Xform V=1
      - 'MATTE': Arnold=254, PV=0, Xform V=1（反射/影には残す）
      - 'HIDE' : Arnold=0,   PV=0, Xform V=0（完全非表示）
      - 'NONE' : 追加のみ
    """
    if not shapes_to_process:
        return None

    logger.debug(f"[VIS] Create under '{parent_collection_name}' action={action}, n={len(shapes_to_process)}")

    try:
        parent_col = layer.createCollection(parent_collection_name)
        if RENDER_SETUP_API_AVAILABLE and hasattr(parent_col.getSelector(), "setPattern"):
            parent_col.getSelector().setPattern("")  # 親は空
    except Exception as e:
        logger.error(f"Create parent collection failed: {e}")
        return None

    if action == "ON":
        arnold_vis, maya_pv, xform_vis = 255, 1, 1
    elif action == "MATTE":
        arnold_vis, maya_pv, xform_vis = 254, 0, 1
    elif action == "HIDE":
        arnold_vis, maya_pv, xform_vis = 0, 0, 0
    else:
        arnold_vis = maya_pv = xform_vis = None

    prefix = {"ON": "TGT", "MATTE": "MAT", "HIDE": "HID", "NONE": "MBR"}.get(action, "MBR")

    for shape in shapes_to_process:
        if not cmds.objExists(shape):
            continue

        has_pv = cmds.attributeQuery("primaryVisibility", node=shape, exists=True)

        parents = cmds.listRelatives(shape, parent=True, fullPath=True) or []
        if not parents and not has_pv:
            continue
        if not parents:
            logger.warning(f"[VIS] parent transform not found: {shape}")
            continue
        xform = parents[0]

        clean = _clean_node_name_for_collection(shape)
        sub_name = f"Col_{prefix}_{clean}"

        try:
            try:
                sub_col = parent_col.createCollection(sub_name)
            except RuntimeError:
                suf = len(cmds.ls(f"{sub_name}*", long=True)) + 1
                sub_col = parent_col.createCollection(f"{sub_name}_{suf}")

            # 静的選択（Transform と Shape を両方）
            if RENDER_SETUP_API_AVAILABLE and hasattr(sub_col.getSelector(), "staticSelection"):
                sub_col.getSelector().staticSelection.set([xform, shape])
            elif RENDER_SETUP_API_AVAILABLE and hasattr(sub_col.getSelector(), "setPattern"):
                sub_col.getSelector().setPattern(f"{xform},{shape}")
                try:
                    sub_col.getSelector().setFilterType(rs_selector.Filters.kAll)  # 可能なら
                except Exception:
                    pass

            if action != "NONE":
                applied = False

                # primaryVisibility（shape）
                if has_pv and (maya_pv is not None):
                    if safe_create_override(sub_col, shape, "primaryVisibility", int(bool(maya_pv))):
                        applied = True

                # Arnold visibility（shape）
                arnold_attr = _choose_arnold_vis_attr(shape)
                if arnold_attr and (arnold_vis is not None):
                    if safe_create_override(sub_col, shape, arnold_attr, int(arnold_vis)):
                        applied = True

                # Transform visibility
                if xform_vis is not None:
                    if safe_create_override(sub_col, xform, "visibility", int(bool(xform_vis))):
                        applied = True

                if not applied:
                    logger.warning(f"[VIS] no overrides actually created: {shape}")

        except Exception as e:
            logger.error(f"[VIS] sub-collection failed for {shape}: {e}")

    return parent_col
