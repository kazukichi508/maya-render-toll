# -*- coding: utf-8 -*-
# render_layer_tool/scene_query.py
from __future__ import annotations
import maya.cmds as cmds
import rs_utils

def get_raw_selection():
    """現在の選択をtransformとして返す。"""
    return cmds.ls(sl=True, long=True, type="transform") or []

def _get_node_type(node_path: str):
    """ノードのタイプと子の有無を判定する。"""
    shapes = cmds.listRelatives(node_path, shapes=True, noIntermediate=True, fullPath=True) or []
    children = cmds.listRelatives(node_path, children=True, type='transform', fullPath=True) or []
    info = {"type": "group" if children or not shapes else "other"}

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
        except Exception: pass
        return None 

    if "light" in inh or "aiLight" in inh:
        info["type"] = "light"
        return info
    
    if "locator" in inh:
        info["type"] = "other"
        return info

    if 'geometry' in inh or cmds.nodeType(shp) == 'mesh':
        info["type"] = "geometry"

    return info

def get_categorized_scene_hierarchy():
    """UIツリー用にカテゴリ分けされた階層データを構築する。"""
    rs_utils.logger.debug("Building categorized scene hierarchy...")
    roots = cmds.ls(assemblies=True, long=True) or []
    
    categorized_hierarchy = {
        "geometry": {},
        "lights": {},
        "cameras": {},
        "groups": {},
        "other": {}
    }

    def build_and_categorize(node_path):
        node_info = _get_node_type(node_path)
        if node_info is None: return None

        node_data = {"type": node_info["type"], "children": {}}
        
        children = cmds.listRelatives(node_path, children=True, type="transform", fullPath=True) or []
        for child in children:
            child_data = build_and_categorize(child)
            if child_data:
                node_data["children"][child] = child_data
        
        return node_data

    ignore = {"|persp", "|top", "|front", "|side", "|defaultLightSet", "|defaultObjectSet"}
    for root_node in roots:
        if root_node in ignore: continue
        
        root_data = build_and_categorize(root_node)
        if root_data:
            category_map = {
                "geometry": "geometry",
                "light": "lights",
                "camera": "cameras",
                "group": "groups",
                "other": "other"
            }
            category = category_map.get(root_data["type"], "other")
            categorized_hierarchy[category][root_node] = root_data

    rs_utils.logger.debug("Categorized hierarchy build complete.")
    return categorized_hierarchy

def get_renderable_descendants(root_node: str):
    """指定ノード配下のレンダリング可能なジオメトリを列挙する。"""
    out = set()
    def is_geom(node: str) -> bool:
        s = cmds.listRelatives(node, shapes=True, noIntermediate=True, fullPath=True) or []
        if not s: return False
        try:
            inh = cmds.nodeType(s[0], inherited=True) or []
            return "camera" not in inh and "light" not in inh and "aiLight" not in inh
        except Exception:
            return False

    if is_geom(root_node):
        out.add(root_node)

    descendants = cmds.listRelatives(root_node, allDescendents=True, type="transform", fullPath=True) or []
    for ch in descendants:
        if is_geom(ch):
            out.add(ch)
    return list(out)

def get_all_renderable_shapes_in_scene():
    """シーン内のレンダリング対象シェイプ（カメラ/ライト除外）を返す。"""
    all_shapes = cmds.ls(type="shape", long=True, noIntermediate=True) or []
    renderable = []
    cache = {}
    for shp in all_shapes:
        try:
            nt = cmds.nodeType(shp)
            if nt not in cache:
                try: cache[nt] = cmds.nodeType(nt, inherited=True) or []
                except: cache[nt] = []
            
            inh = cache[nt]
            if "camera" in inh or "light" in inh or "aiLight" in inh:
                continue
            renderable.append(shp)
        except Exception:
            pass
    return renderable

def get_shapes_from_transforms(transform_nodes: list[str]) -> list[str]:
    """トランスフォームノードリストから関連するシェイプを返す。"""
    if not transform_nodes: return []
    shapes = cmds.listRelatives(transform_nodes, shapes=True, noIntermediate=True, fullPath=True, allDescendents=True) or []
    return sorted(list(set(shapes)))

