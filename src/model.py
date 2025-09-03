# -*- coding: utf-8 -*-
# render_layer_tool/model.py
"""
Model層のファサード（Facade）。
"""
# --- 修正: 相対インポートから直接インポートに変更 ---
from rs_utils import logger
from scene_query import (
    get_raw_selection,
    get_scene_hierarchy,
    get_renderable_descendants,
)
from layers import (
    create_render_layer,
    create_layers_for_each_solo_object,
    get_all_render_layers,
    delete_render_layers,
    delete_all_render_layers
)

