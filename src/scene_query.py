# render_layer_tool/scene_query.py
# -*- coding: utf-8 -*-
"""
Mayaシーンの情報を取得・整理するためのモジュール。
"""
import maya.cmds as cmds
import logging

def get_node_type(path):
    """ノードパスからノードタイプを推測し、Viewのアイコン表示用に分類する。"""
    try:
        if not cmds.objExists(path):
            return 'default'
        
        # トランスフォームノードの場合、シェイプを確認する
        if cmds.objectType(path, isType='transform'):
            # 中間オブジェクトを除いたシェイプを取得
            shapes = cmds.listRelatives(path, shapes=True, fullPath=True, noIntermediate=True)
            if shapes:
                shape_type = cmds.nodeType(shapes[0])
                if shape_type in ['mesh', 'nurbsSurface', 'subdiv']:
                    return 'geometry'
                elif 'camera' in shape_type:
                    return 'camera'
                # Arnoldなどの外部レンダラのライトも考慮
                elif 'light' in shape_type or 'Light' in shape_type:
                    return 'light'
            
            # シェイプを持たず、子トランスフォームがある場合はグループとみなす
            if cmds.listRelatives(path, children=True, type='transform', fullPath=True):
                return 'group'
        
        return 'other'
    except Exception as e:
        logging.warning(f"Error determining node type for {path}: {e}")
        return 'default'

def is_renderable(path):
    """ノードがレンダリング対象（ジオメトリやライト）であるかを判定する。"""
    node_type = get_node_type(path)
    return node_type in ['geometry', 'light']

def get_scene_hierarchy():
    """
    シーン内の主要なオブジェクトの階層構造を取得し、View用に分類する。
    """
    # トップレベルのDAGノードを取得
    all_assemblies = cmds.ls(assemblies=True, long=True)
    
    # 標準カメラを除外
    std_cameras = set(['|persp', '|top', '|front', '|side'])
    
    hierarchy = {"groups": {}, "objects": {}, "other": {}}

    def build_hierarchy_recursive(path, parent_dict):
        if not cmds.objExists(path):
            return

        node_data = {}
        node_type = get_node_type(path)
        node_data['type'] = node_type
        
        # 子のトランスフォームノードを取得して再帰処理
        children = cmds.listRelatives(path, children=True, fullPath=True, type='transform')
        if children:
            node_data['children'] = {}
            for child in children:
                 build_hierarchy_recursive(child, node_data['children'])

        parent_dict[path] = node_data

    # トップレベルノードを分類して階層構築
    for assembly in all_assemblies:
        if assembly in std_cameras:
            continue

        if is_renderable(assembly):
            category = "objects"
        elif get_node_type(assembly) == 'group':
            category = "groups"
        else:
            category = "other"
            
        if assembly not in hierarchy[category]:
            build_hierarchy_recursive(assembly, hierarchy[category])

    return hierarchy

def get_selected_paths():
    """現在選択されているオブジェクトのフルパスリストを取得する。"""
    return cmds.ls(selection=True, long=True) or []

def resolve_selection(paths, expand_groups=True):
    """指定されたパスリストを解決する。
       expand_groupsがTrueの場合、グループを展開して子孫のレンダリング可能ノードを取得する。
    """
    resolved = set()
    
    if not expand_groups:
        # 展開しない場合は、選択されたノード（グループ含む）をそのまま追加
        for path in paths:
            if cmds.objExists(path):
                resolved.add(path)
        return list(resolved)

    # 展開する場合
    for path in paths:
        if not cmds.objExists(path):
            continue
        
        # 自身がレンダリング可能なら追加
        if is_renderable(path):
            resolved.add(path)
            
        # 子孫を探索（トランスフォームノードのみ対象）
        descendants = cmds.listRelatives(path, allDescendents=True, fullPath=True, type='transform') or []
        for desc in descendants:
            if is_renderable(desc):
                resolved.add(desc)
                
    # パスが短い順にソートして返す
    return sorted(list(resolved), key=lambda x: len(x.split('|')))