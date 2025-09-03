# -*- coding: utf-8 -*-
# render_layer_tool/model.py
"""
Model層のファサード（Facade）。
"""
# rs_utilsからロガーをインポートして使用
from .rs_utils import logger

# scene_query.py から公開
# ※scene_query.pyが正しく実装されている必要があります。
try:
    from .scene_query import (
        get_raw_selection,
        get_scene_hierarchy,
        get_renderable_descendants,
    )
except ImportError as e:
    logger.error(f"Failed to import from scene_query.py: {e}", exc_info=True)
    # ダミー関数
    def get_raw_selection(): return []
    def get_scene_hierarchy(): return {}
    def get_renderable_descendants(*args): return []

# layers.py から公開
# これにより controller.py は model.delete_render_layers() のようにアクセスできる
try:
    from .layers import (
        create_render_layer,
        create_layers_for_each_solo_object,
        get_all_render_layers,
        delete_render_layers,
        delete_all_render_layers
    )
except ImportError as e:
    logger.error(f"Failed to import from layers.py: {e}", exc_info=True)
    # ダミー関数
    def create_render_layer(*args, **kwargs): return False
    def create_layers_for_each_solo_object(*args, **kwargs): return 0, 0
    def get_all_render_layers(): return []
    def delete_render_layers(*args): return False
    def delete_all_render_layers(): return False