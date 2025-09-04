# render_layer_tool/controller.py
# -*- coding: utf-8 -*-
"""
Viewからのユーザー入力を受け取り、Modelと連携してUIを更新するController層。
"""
import maya.cmds as cmds
import maya.OpenMaya as om

from PySide6 import QtWidgets, QtCore

class RenderLayerController:
    """
    ModelとViewを仲介するコントローラークラス。
    """
    def __init__(self, model, view):
        self.model = model
        self.view = view
        
        self._is_syncing = False
        self._callback_ids = []

        self._connect_signals()
        self._install_callbacks()
        
        self.refresh_all_ui()

    def _connect_signals(self):
        self.view.request_populate_tree.connect(self.refresh_scene_tree)
        self.view.scene_objects_tree.itemSelectionChanged.connect(self.on_tree_selection_changed)
        self.view.request_add_to_target.connect(self.on_add_to_list)
        self.view.request_remove_from_target.connect(self.on_remove_from_list)
        self.view.request_create_layer.connect(self.on_create_layer)
        self.view.request_layer_list_refresh.connect(self.refresh_layer_list)
        self.view.request_delete_selected_layers.connect(self.on_delete_selected)
        self.view.request_delete_all_layers.connect(self.on_delete_all)
        self.view.widget_closed.connect(self.cleanup)

    def _install_callbacks(self):
        """Mayaのシーン変更を検知するためのコールバックをインストールします。"""
        # --- ★★ここを修正★★ ---
        # "DagObjectDeleted" をリストから削除し、より安定した "delete" 条件を個別に追加
        events = ["DagObjectCreated", "NameChanged", "Undo", "Redo"]
        for event in events:
            try:
                job_id = cmds.scriptJob(event=[event, self.refresh_scene_tree], protected=True)
                self._callback_ids.append(job_id)
            except Exception as e:
                print(f"Failed to install scriptJob for {event}: {e}")
        
        # オブジェクト削除は 'conditionTrue' (ct) で監視する
        try:
            delete_job_id = cmds.scriptJob(ct=["delete", self.refresh_scene_tree], protected=True)
            self._callback_ids.append(delete_job_id)
        except Exception as e:
            print(f"Failed to install scriptJob for delete condition: {e}")
        # -------------------------

        selection_cb_id = om.MEventMessage.addEventCallback("SelectionChanged", self.on_maya_selection_changed)
        self._callback_ids.append(selection_cb_id)

    def cleanup(self):
        """ツール終了時にコールバックをすべて解除します。"""
        for cb_id in self._callback_ids:
            try:
                if isinstance(cb_id, int): # scriptJob ID
                    if cmds.scriptJob(exists=cb_id):
                        cmds.scriptJob(kill=cb_id, force=True)
                else: # MMessage ID
                    om.MMessage.removeCallback(cb_id)
            except Exception:
                pass # Maya終了時などにエラーが出ることがあるが無視してよい
        self._callback_ids = []
        print("Cleaned up callbacks.")

    def refresh_all_ui(self):
        self.refresh_scene_tree()
        self.refresh_layer_list()

    def refresh_scene_tree(self):
        hierarchy = self.model.get_scene_hierarchy()
        self.view.populate_scene_tree_hierarchy(hierarchy)
        self.sync_tree_with_maya_selection()

    def refresh_layer_list(self):
        layers = self.model.get_all_layers()
        self.view.populate_render_layer_list(layers)

    def on_create_layer(self):
        layer_name = self.view.layer_name_le.text()
        targets = [self.view.target_list_widget.item(i).text() for i in range(self.view.target_list_widget.count())]
        pv_off = [self.view.pvoff_list_widget.item(i).text() for i in range(self.view.pvoff_list_widget.count())]
        
        if not layer_name:
            self.view.set_status("エラー: レイヤー名を入力してください。", color="#F44336")
            return
            
        success = self.model.create_layer(layer_name, targets, pv_off)
        if success:
            self.view.set_status(f"レイヤー '{layer_name}' を作成しました。", color="#7EE081")
            self.refresh_layer_list()
        else:
            self.view.set_status("レイヤーの作成に失敗しました。", color="#F44336")

    def on_delete_selected(self):
        selected_items = self.view.layer_list_widget.selectedItems()
        layer_names = [item.text() for item in selected_items]
        if not layer_names or not self._confirm_dialog("選択したレイヤーを削除しますか？"):
            return
            
        self.model.delete_layers(layer_names)
        self.refresh_layer_list()

    def on_delete_all(self):
        if not self._confirm_dialog("本当にすべてのレンダーレイヤーを削除しますか？\nこの操作は元に戻せません。", is_warning=True):
            return
            
        self.model.delete_all_layers()
        self.refresh_layer_list()
    
    def on_add_to_list(self, list_name: str):
        target_widget = self.view.target_list_widget if list_name == 'target' else self.view.pvoff_list_widget
        selected_items = self.view.scene_objects_tree.selectedItems()
        
        current_list_items = {target_widget.item(i).text() for i in range(target_widget.count())}
        
        for item in selected_items:
            path = item.data(0, QtCore.Qt.UserRole)
            if path and path not in current_list_items:
                target_widget.addItem(path)

    def on_remove_from_list(self, list_name: str):
        target_widget = self.view.target_list_widget if list_name == 'target' else self.view.pvoff_list_widget
        for item in target_widget.selectedItems():
            target_widget.takeItem(target_widget.row(item))

    def on_tree_selection_changed(self):
        if self._is_syncing: return
        self._is_syncing = True
        selected_paths = [item.data(0, QtCore.Qt.UserRole) for item in self.view.scene_objects_tree.selectedItems()]
        if selected_paths:
            cmds.select([path for path in selected_paths if cmds.objExists(path)], r=True)
        else:
            cmds.select(clear=True)
        self._is_syncing = False

    def on_maya_selection_changed(self, *args, **kwargs):
        if self._is_syncing: return
        self.sync_tree_with_maya_selection()

    def sync_tree_with_maya_selection(self):
        self._is_syncing = True
        selected_paths = self.model.get_selection()
        self.view.sync_tree_selection(selected_paths)
        self._is_syncing = False

    def _confirm_dialog(self, message: str, is_warning: bool = False) -> bool:
        msg_box = QtWidgets.QMessageBox(self.view)
        msg_box.setText(message)
        msg_box.setStandardButtons(QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
        msg_box.setDefaultButton(QtWidgets.QMessageBox.No)
        icon = QtWidgets.QMessageBox.Warning if is_warning else QtWidgets.QMessageBox.Question
        msg_box.setIcon(icon)
        return msg_box.exec() == QtWidgets.QMessageBox.Yes