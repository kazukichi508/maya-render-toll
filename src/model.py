# -*- coding: utf-8 -*-
# render_layer_tool/model.py
"""
Model層のファサード（Facade）。
各専門モジュール（scene_query, layersなど）の機能を仲介する。
"""
import rs_utils

# --- scene_query.py からの機能 ---
import scene_query

def get_raw_selection():
    """scene_queryのget_raw_selectionを公開する。"""
    return scene_query.get_raw_selection()

def get_categorized_scene_hierarchy():
    """【修正】scene_queryの正しい関数名を呼び出すように変更。"""
    return scene_query.get_categorized_scene_hierarchy()

def get_renderable_descendants(root_node):
    """scene_queryのget_renderable_descendantsを公開する。"""
    return scene_query.get_renderable_descendants(root_node)

# --- layers.py からの機能 ---
import layers

def create_render_layer(layer_name, target_objects, pv_off_objects, auto_matte, aov_settings):
    """layersのcreate_render_layerを公開する。"""
    return layers.create_render_layer(layer_name, target_objects, pv_off_objects, auto_matte, aov_settings)

def create_layers_for_each_solo_object(solo_objects, pv_off_objects, aov_settings, auto_matte):
    """layersのcreate_layers_for_each_solo_objectを公開する。"""
    return layers.create_layers_for_each_solo_object(solo_objects, pv_off_objects, aov_settings, auto_matte)

def get_all_render_layers():
    """layersのget_all_render_layersを公開する。"""
    return layers.get_all_render_layers()

def delete_render_layers(layer_names_to_delete):
    """layersのdelete_render_layersを公開する。"""
    return layers.delete_render_layers(layer_names_to_delete)

def delete_all_render_layers():
    """layersのdelete_all_render_layersを公開する。"""
    return layers.delete_all_render_layers()

