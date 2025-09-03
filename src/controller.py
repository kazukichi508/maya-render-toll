# -*- coding: utf-8 -*-
# render_layer_tool/controller.py

from PySide6 import QtWidgets, QtCore, QtGui

# --- 修正: 相対インポートから直接インポートに変更 ---
import model
from rs_utils import logger, RENDER_SETUP_API_AVAILABLE

import maya.cmds as cmds
import maya.OpenMaya as om

if RENDER_SETUP_API_AVAILABLE:
    try:
        from maya.app.renderSetup.model import renderSetup
    except ImportError:
        renderSetup = None
else:
    renderSetup = None


class RenderLayerToolController:
    """ViewとModelをつなぐコントローラー。"""
    def __init__(self, view_instance):
        self.view = view_instance
        self._script_jobs = []
        self._callback_ids = []
        self._rs_callbacks = {}
        self._is_syncing_selection = False

        self.tree_refresh_timer = QtCore.QTimer()
        self.tree_refresh_timer.setSingleShot(True)
        self.tree_refresh_timer.setInterval(250)

        self._connect()
        self._install_callbacks() 
        self.populate_tree()
        self.refresh_layer_management_list()
        
        logger.info("Controller initialized successfully.")

    def _connect(self):
        v = self.view
        v.request_populate_tree.connect(self._trigger_tree_refresh)
        v.request_add_to_target.connect(self._on_add_to_list)
        v.request_remove_from_target.connect(self._on_remove_from_list)
        v.request_create_layer.connect(self._on_create_layer)
        v.request_layer_list_refresh.connect(self.refresh_layer_management_list)
        v.request_delete_selected_layers.connect(self._on_delete_selected_layers)
        v.request_delete_all_layers.connect(self._on_delete_all_layers)
        v.widget_closed.connect(self.cleanup)
        v.scene_objects_tree.itemSelectionChanged.connect(self._on_tree_selection_changed)
        v.search_text_changed.connect(self.filter_tree)
        v.request_apply_aov_preset.connect(self.apply_aov_preset)

        try:
            for widget in [v.target_list_widget, v.pvoff_list_widget]:
                widget.model().rowsInserted.connect(self._suggest_layer_name)
                widget.model().rowsRemoved.connect(self._suggest_layer_name)
        except AttributeError:
            logger.warning("Could not connect list widgets for layer name suggestion.")

        self.tree_refresh_timer.timeout.connect(self.populate_tree)
        logger.debug("UI signals connected.")

    def show(self):
        self.view.show()

    def _install_callbacks(self):
        logger.info("Installing callbacks.")
        events = ["DagObjectCreated", "NameChanged", 'Undo', 'Redo', 'parent']
        for event in events:
            try:
                job_id = cmds.scriptJob(event=[event, self._trigger_tree_refresh], protected=True)
                self._script_jobs.append(job_id)
            except Exception as e:
                logger.warning(f"Failed to install ScriptJob for event '{event}': {e}")
        try:
            job_id = cmds.scriptJob(ct=["delete", self._trigger_tree_refresh], protected=True)
            self._script_jobs.append(job_id)
        except Exception as e:
            logger.warning(f"Failed to install ScriptJob for 'delete': {e}")
        try:
            cb_id = om.MEventMessage.addEventCallback("SelectionChanged", self._on_maya_selection_changed)
            self._callback_ids.append(cb_id)
        except Exception as e:
            logger.error(f"Failed to install selection callback (MEventMessage): {e}")
        if RENDER_SETUP_API_AVAILABLE and renderSetup:
            try:
                self._rs_callbacks = {'add': self._on_render_setup_changed, 'remove': self._on_render_setup_changed}
                rs = renderSetup.instance()
                if rs:
                    try:
                        rs.renderLayers.add.disconnect(self._rs_callbacks['add'])
                        rs.renderLayers.remove.disconnect(self._rs_callbacks['remove'])
                    except Exception: pass
                    rs.renderLayers.add.connect(self._rs_callbacks['add'])
                    rs.renderLayers.remove.connect(self._rs_callbacks['remove'])
            except Exception as e:
                logger.warning(f"Failed to setup Render Setup callbacks: {e}.")

    def cleanup(self):
        logger.info("Cleaning up callbacks and resources.")
        for job_id in self._script_jobs:
            try:
                if cmds.scriptJob(exists=job_id): cmds.scriptJob(kill=job_id, force=True)
            except Exception: pass
        self._script_jobs = []
        for cb_id in self._callback_ids:
            try: om.MMessage.removeCallback(cb_id)
            except Exception: pass
        self._callback_ids = []
        if RENDER_SETUP_API_AVAILABLE and renderSetup and self._rs_callbacks:
            try:
                rs = renderSetup.instance()
                if rs:
                    rs.renderLayers.add.disconnect(self._rs_callbacks['add'])
                    rs.renderLayers.remove.disconnect(self._rs_callbacks['remove'])
            except Exception: pass
        if self.tree_refresh_timer.isActive(): self.tree_refresh_timer.stop()
        logger.info("Cleanup complete.")

    def _on_render_setup_changed(self, *args, **kwargs):
        QtCore.QTimer.singleShot(50, self.refresh_layer_management_list)

    def _trigger_tree_refresh(self, *args, **kwargs):
        self.tree_refresh_timer.start()

    def populate_tree(self, *args, **kwargs):
        logger.debug("Executing populate_tree.")
        scene_hierarchy = model.get_scene_hierarchy()
        try:
            self.view.populate_scene_tree_hierarchy(scene_hierarchy)
            self.filter_tree(self.view.search_le.text())
        except AttributeError:
            logger.warning("View methods for tree population missing.")
        self._on_maya_selection_changed()

    def filter_tree(self, text):
        try: self.view.filter_scene_tree(text)
        except AttributeError: pass

    def _on_maya_selection_changed(self, *args, **kwargs):
        if self._is_syncing_selection: return
        self._is_syncing_selection = True
        try:
            self.view.scene_objects_tree.blockSignals(True)
            current_selection = model.get_raw_selection()
            self.view.sync_tree_selection(current_selection)
        except AttributeError:
             logger.warning("View methods for selection sync missing.")
        finally:
            try: self.view.scene_objects_tree.blockSignals(False)
            except AttributeError: pass
            self._is_syncing_selection = False

    def _on_tree_selection_changed(self):
        if self._is_syncing_selection: return
        self._is_syncing_selection = True
        try:
            selected_items = self.view.scene_objects_tree.selectedItems()
            paths = [it.data(0, QtCore.Qt.UserRole) for it in selected_items if it.data(0, QtCore.Qt.UserRole)]
            if paths:
                valid_paths = [p for p in paths if cmds.objExists(p)]
                if valid_paths: cmds.select(valid_paths, r=True)
                else: cmds.select(cl=True)
            elif not selected_items: cmds.select(cl=True)
        except AttributeError:
             logger.warning("View methods for selection sync missing.")
        finally:
            self._is_syncing_selection = False

    def _get_list_widgets(self, list_name):
        try:
            if list_name == 'target':
                return self.view.target_list_widget, self.view.pvoff_list_widget
            elif list_name == 'pvoff':
                return self.view.pvoff_list_widget, self.view.target_list_widget
        except AttributeError:
            logger.warning("List widgets missing in View.")
        return None, None
        
    def _on_add_to_list(self, list_name): pass
    def _on_remove_from_list(self, list_name): pass
    def _suggest_layer_name(self): pass
    def _on_create_layer(self): pass
    def apply_aov_preset(self, preset_name): pass

    def refresh_layer_management_list(self):
        logger.debug("Executing refresh_layer_management_list.")
        try:
            selected_layers = [item.text() for item in self.view.layer_list_widget.selectedItems()]
            layers = model.get_all_render_layers()
            self.view.populate_render_layer_list(layers)
            for i in range(self.view.layer_list_widget.count()):
                item = self.view.layer_list_widget.item(i)
                if item.text() in selected_layers: item.setSelected(True)
        except AttributeError:
            logger.warning("View methods for layer management missing.")

    def _on_delete_selected_layers(self):
        logger.debug("[DIAG-Ctrl] Delete Selected Layers button clicked.")
        try:
            layer_names = [item.text() for item in self.view.layer_list_widget.selectedItems()]
        except AttributeError:
             logger.error("Cannot access layer_list_widget in View.")
             return
        if not layer_names: return
        
        reply = QtWidgets.QMessageBox.question(self.view, '削除の確認', f"{len(layer_names)} 件のレイヤーを削除しますか？\n\n- " + "\n- ".join(layer_names), QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No, QtWidgets.QMessageBox.No)
        if reply == QtWidgets.QMessageBox.Yes:
            logger.warning(f"[DIAG-Ctrl] User CONFIRMED deletion of: {layer_names}")
            model.delete_render_layers(layer_names)
            self.refresh_layer_management_list()
        else:
            logger.info("[DIAG-Ctrl] User CANCELLED deletion.")

    def _on_delete_all_layers(self):
        logger.debug("[DIAG-Ctrl] Delete ALL Layers button clicked.")
        reply = QtWidgets.QMessageBox.warning(self.view, '最終確認', "全てのレンダーレイヤーを削除します。\nこの操作は元に戻せません。よろしいですか？", QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No, QtWidgets.QMessageBox.No)
        if reply == QtWidgets.QMessageBox.Yes:
            logger.warning("[DIAG-Ctrl] User CONFIRMED deletion of ALL layers.")
            model.delete_all_render_layers()
            self.refresh_layer_management_list()
        else:
            logger.info("[DIAG-Ctrl] User CANCELLED deletion.")

