# -*- coding: utf-8 -*-
# render_layer_tool/scene_query.py
from __future__ import annotations
import maya.cmds as cmds
# rs_utils のインポートを削除

# --- ここから修正箇所 ---

# rs_utils.py の代替となるシンプルなログ機能
class SimpleLogger:
    def info(self, msg): print(f"INFO: {msg}")
    def debug(self, msg): print(f"DEBUG: {msg}")
    def warning(self, msg): print(f"WARNING: {msg}")
    def error(self, msg): print(f"ERROR: {msg}")
logger = SimpleLogger()

# --- 修正箇所ここまで ---

def get_raw_selection():
    """現在の選択をtransformとして返す。"""
    return cmds.ls(sl=True, long=True, type="transform") or []

def _get_node_type(node_path: str):
    """ノードのタイプと子の有無を判定する。"""
    shapes = cmds.listRelatives(node_path, shapes=True, noIntermediate=True, fullPath=True) or []
    children = cmds.listRelatives(node_path, children=True, type='transform', fullPath=True) or []
    info = {"type": "group" if children and not shapes else "other"}

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
    """UIツリー用に「グループ」「オブジェクト」「その他」の3つにカテゴリ分けされた階層データを構築する。"""
    logger.debug("Building scene hierarchy...")
    
    categorized_hierarchy = {
        "groups": {},
        "objects": {},
        "other": {}
    }

    def build_full_hierarchy(node_path):
        node_info = _get_node_type(node_path)
        if node_info is None:
            return None

        node_data = {"type": node_info["type"], "children": {}}
        
        children = cmds.listRelatives(node_path, children=True, type="transform", fullPath=True) or []
        for child in children:
            child_data = build_full_hierarchy(child)
            if child_data:
                node_data["children"][child] = child_data
        
        return node_data

    root_nodes = cmds.ls(assemblies=True, long=True) or []
    ignore_list = {"|persp", "|top", "|front", "|side", "|defaultLightSet", "|defaultObjectSet"}

    for root in root_nodes:
        if root in ignore_list:
            continue

        hierarchy_data = build_full_hierarchy(root)

        if hierarchy_data:
            root_type = hierarchy_data["type"]
            
            if root_type == "group":
                categorized_hierarchy["groups"][root] = hierarchy_data
            elif root_type in ["geometry", "light", "camera"]:
                categorized_hierarchy["objects"][root] = hierarchy_data
            else:
                categorized_hierarchy["other"][root] = hierarchy_data
    
    logger.debug(f"Categorized hierarchy complete.")
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