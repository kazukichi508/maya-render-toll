# -*- coding: utf-8 -*-
# render_layer_tool/layers.py
from __future__ import annotations
import maya.cmds as cmds

# 関連モジュールをインポート
import rs_utils
import scene_query
import aov

# visibility.py のインポートは不要になりました

RENDER_LAYER_API_AVAILABLE = False
renderLayer = None
try:
    from maya.app.renderSetup.model import renderLayer
    RENDER_LAYER_API_AVAILABLE = True
except ImportError:
    rs_utils.logger.error("CRITICAL: Could not import renderLayer model API.", exc_info=True)


def _create_collections_by_shapes(layer, parent_collection_name: str, shapes_to_process, action: str):
    """
    【統合された関数】シェイプごとにサブコレクションを作成し、可視性オーバーライドを適用する。
    """
    if not shapes_to_process:
        return None

    rs_utils.logger.debug(f"Create collections under '{parent_collection_name}' (action={action}, n={len(shapes_to_process)})")

    try:
        parent_col = layer.createCollection(parent_collection_name)
    except Exception as e:
        rs_utils.logger.error(f"Create parent collection failed: {e}")
        return None

    if action == "ON":
        arnold_vis, maya_pv, xform_vis = 255, 1, 1
    elif action == "MATTE":
        arnold_vis, maya_pv, xform_vis = 254, 0, 1
    else: # NONE
        arnold_vis = maya_pv = xform_vis = None

    prefix = {"ON": "TGT", "MATTE": "MAT", "NONE": "MBR"}.get(action, "MBR")

    for shape in shapes_to_process:
        if not cmds.objExists(shape): continue

        parents = cmds.listRelatives(shape, parent=True, fullPath=True) or []
        if not parents: continue
        xform = parents[0]

        clean_name = rs_utils._clean_node_name_for_collection(shape)
        sub_name = f"Col_{prefix}_{clean_name}"

        try:
            try:
                sub_col = parent_col.createCollection(sub_name)
            except RuntimeError: # 名前重複時のフォールバック
                suf = len(cmds.ls(f"{sub_name}*", long=True)) + 1
                sub_col = parent_col.createCollection(f"{sub_name}_{suf}")
            
            # 静的選択でトランスフォームとシェイプを両方含める
            sel = sub_col.getSelector()
            if hasattr(sel, 'staticSelection'):
                sel.staticSelection.set([xform, shape])

            if action != "NONE":
                # Primary Visibility (shape)
                if cmds.attributeQuery("primaryVisibility", node=shape, exists=True):
                    rs_utils.safe_create_override(sub_col, shape, "primaryVisibility", maya_pv)
                # Arnold Visibility (shape) - Maya 2024+
                if cmds.attributeQuery("aiVisibility", node=shape, exists=True):
                    rs_utils.safe_create_override(sub_col, shape, "aiVisibility", arnold_vis)
                # Transform visibility
                rs_utils.safe_create_override(sub_col, xform, "visibility", xform_vis)
        except Exception as e:
            rs_utils.logger.error(f"Sub-collection failed for {shape}: {e}")

    return parent_col


def create_render_layer(layer_name, target_objects, pv_off_objects, auto_matte, aov_settings):
    rs_utils.logger.info(f"--- Starting layer creation for '{layer_name}' (AutoMatte: {auto_matte}) ---")
    if not layer_name:
        rs_utils.logger.error("Layer name is required.")
        return False
    
    rs = rs_utils.get_render_setup_instance()
    if not rs: return False
    rs_utils.ensure_arnold_renderer()

    try:
        # レイヤー取得/作成
        layer = rs_utils.get_or_create_layer(rs, layer_name)
        if not layer: return False

        # 既存コレクションのクリア
        for col in reversed(list(layer.getCollections())):
            try:
                layer.removeCollection(col)
            except Exception as e:
                rs_utils.logger.warning(f"Failed to remove collection {col.name()}: {e}")

        # シェイプの計算
        target_shapes = scene_query.get_shapes_from_transforms(target_objects)
        pv_off_shapes = scene_query.get_shapes_from_transforms(pv_off_objects)
        
        matte_shapes = []
        if auto_matte:
            all_scene_shapes = set(scene_query.get_all_renderable_shapes_in_scene())
            processed_shapes = set(target_shapes + pv_off_shapes)
            matte_shapes = sorted(list(all_scene_shapes - processed_shapes))

        # コレクション作成（内部関数を呼び出すように変更）
        _create_collections_by_shapes(layer, f"{layer_name}_TARGETS", target_shapes, "ON")
        _create_collections_by_shapes(layer, f"{layer_name}_PV_OFF", pv_off_shapes, "MATTE")
        if matte_shapes:
            _create_collections_by_shapes(layer, f"{layer_name}_AUTO_MATTE", matte_shapes, "MATTE")

        # AOV設定
        aov.setup_aov_collections(layer, layer_name, aov_settings)

        rs.switchToLayer(layer)
        rs_utils.logger.info(f"--- Successfully finished layer creation for '{layer_name}' ---")
        return True
    except Exception as e:
        rs_utils.logger.error(f"An exception occurred during layer creation: {e}", exc_info=True)
        try:
            rs_utils._safe_switch_to_master(rs)
        except Exception: pass
        return False

def create_layers_for_each_solo_object(solo_objects, pv_off_objects, aov_settings, auto_matte):
    if not solo_objects: return 0, 0
    success_count = 0
    total = len(solo_objects)
    rs_utils.logger.info(f"--- Starting individual layer creation for {total} objects ---")

    for i, solo_obj in enumerate(solo_objects):
        clean_name = rs_utils._clean_node_name_for_collection(solo_obj)
        layer_name = f"RL_{clean_name}"
        rs_utils.logger.info(f"({i+1}/{total}) Processing: '{solo_obj}'")
        
        ok = create_render_layer(layer_name, [solo_obj], pv_off_objects, auto_matte, aov_settings)
        if ok: success_count += 1
        
    rs_utils.logger.info(f"--- Finished individual layer creation. Success: {success_count}/{total} ---")
    return success_count, total

def get_all_render_layers() -> list[str]:
    rs = rs_utils.get_render_setup_instance()
    if not rs: return []
    try:
        return [layer.name() for layer in rs.getRenderLayers() if not layer.isDefaultLayer()]
    except Exception as e:
        rs_utils.logger.error(f"Failed to get render layers: {e}", exc_info=True)
        return []

def delete_render_layers(layer_names_to_delete: list[str]) -> bool:
    rs = rs_utils.get_render_setup_instance()
    if not rs or not RENDER_LAYER_API_AVAILABLE:
        return False
        
    if not rs_utils._safe_switch_to_master(rs):
        rs_utils.logger.error("Failed to switch to master layer. Aborting deletion.")
        return False
    
    success_count = 0
    for name in layer_names_to_delete:
        try:
            layer_obj = rs.getRenderLayer(name)
            if layer_obj and not layer_obj.isDefaultLayer():
                renderLayer.delete(layer_obj)
                success_count += 1
                rs_utils.logger.info(f"Successfully deleted layer: {name}")
        except Exception:
            rs_utils.logger.error(f"FAILED to delete layer '{name}'.", exc_info=True)
            
    return success_count > 0

def delete_all_render_layers() -> bool:
    layers_to_delete = get_all_render_layers()
    if not layers_to_delete:
        rs_utils.logger.info("No render layers to delete.")
        return True
    return delete_render_layers(layers_to_delete)

