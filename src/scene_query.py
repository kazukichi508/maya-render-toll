# -*- coding: utf-8 -*-
# render_layer_tool/scene_query.py
from __future__ import annotations
import maya.cmds as cmds
# --- 修正: 相対インポートから直接インポートに変更 ---
from rs_utils import _ensure_mtoa_loaded, logger

def get_raw_selection():
    """現在選択の transform (long path) を返す"""
    return cmds.ls(sl=True, long=True, type="transform") or []

def _get_node_type(node_path: str):
    _ensure_mtoa_loaded()
    shapes = cmds.listRelatives(node_path, shapes=True, noIntermediate=True, fullPath=True) or []
    info = {"type": "group", "primaryVisibility": None}
    if not shapes:
        return info

    shp = shapes[0]
    try:
        inh = cmds.nodeType(shp, inherited=True) or []
    except Exception:
        inh = []

    if "camera" in inh:
        try:
            if not cmds.camera(node_path, q=True, startupCamera=True):
                info["type"] = "camera"
                return info
            else:
                return None # スタートアップカメラは無視
        except Exception:
            return None

    is_light = "light" in inh or "aiLight" in inh
    if not is_light and cmds.nodeType(shp) in ("aiAreaLight", "aiSkyDomeLight", "aiMeshLight", "aiPhotometricLight"):
        is_light = True
    if is_light:
        info["type"] = "light"
        return info

    if "locator" in inh:
        info["type"] = "other"
        return info

    info["type"] = "geometry"
    if cmds.attributeQuery("primaryVisibility", node=shp, exists=True):
        try: info["primaryVisibility"] = cmds.getAttr(f"{shp}.primaryVisibility")
        except Exception: pass
    return info

def get_scene_hierarchy():
    logger.debug("Building scene hierarchy.")
    roots = cmds.ls(assemblies=True, long=True) or []
    hierarchy = {}

    def build(n):
        inf = _get_node_type(n)
        if inf is None: return None
        data = {"type": inf["type"], "primaryVisibility": inf["primaryVisibility"], "children": {}}
        kids = cmds.listRelatives(n, children=True, type="transform", fullPath=True) or []
        for ch in kids:
            s = build(ch)
            if s: data["children"][ch] = s
        return data

    ignore = {"|persp", "|top", "|front", "|side"}
    for n in roots:
        if n in ignore: continue
        d = build(n)
        if d: hierarchy[n] = d

    logger.debug("Hierarchy building complete.")
    return hierarchy

def get_renderable_descendants(root_node: str):
    """root_node 配下のレンダリング可能 transform を列挙"""
    out = set()
    def is_geom(node: str):
        s = cmds.listRelatives(node, shapes=True, noIntermediate=True, fullPath=True) or []
        if not s: return False
        try:
            inh = cmds.nodeType(s[0], inherited=True) or []
        except Exception: inh = []
        return "camera" not in inh and "light" not in inh and "aiLight" not in inh

    if is_geom(root_node): out.add(root_node)
    for ch in cmds.listRelatives(root_node, allDescendents=True, type="transform", fullPath=True) or []:
        if is_geom(ch): out.add(ch)
    return list(out)

def get_all_renderable_shapes_in_scene():
    """シーン内のレンダリング対象 shape（camera/light を除外）"""
    out = []
    cache = {}
    for shp in cmds.ls(type="shape", long=True, noIntermediate=True) or []:
        try:
            nt = cmds.nodeType(shp)
            if nt not in cache:
                try: cache[nt] = cmds.nodeType(nt, inherited=True) or []
                except Exception: cache[nt] = []
            inh = cache[nt]
            if "camera" in inh or "light" in inh or "aiLight" in inh:
                continue
            out.append(shp)
        except Exception: pass
    return out

