# render_layer_tool/controller.py
# -*- coding: utf-8 -*-
"""
ViewとModelを仲介し、アプリケーションのロジックを制御するコントローラー。
"""
import maya.cmds as cmds
from maya.api import OpenMaya as om
from PySide6 import QtWidgets, QtCore

import model
import scene_query

class RenderLayerToolController:
    """
    UIからのイベントを処理し、モデルとビューを更新する。
    """
    def __init__(self, view_instance):
        self.view = view_instance
        self.model = model.RenderLayerManager()
        self._callback_ids = []
        
        self._connect_signals()
        self._setup_maya_callbacks()

        self.populate_scene_tree()
        self.refresh_render_layer_list()

    def cleanup(self):
        """ツール終了時にコールバックをクリーンアップする。"""
        if self._callback_ids:
            om.MMessage.removeCallbacks(self._callback_ids)
            self._callback_ids = []
            print("Maya Callbacks removed.")

    def _connect_signals(self):
        """ViewからのシグナルをControllerのスロットに接続する。"""
        self.view.request_populate_tree.connect(self.populate_scene_tree)
        self.view.request_add_to_target.connect(self._add_selected_to_list)
        self.view.request_remove_from_target.connect(self._remove_selected_from_list)
        self.view.request_create_layer.connect(self.create_render_layer)
        self.view.request_layer_list_refresh.connect(self.refresh_render_layer_list)
        self.view.request_delete_selected_layers.connect(self.delete_selected_layers)
        self.view.request_delete_all_layers.connect(self.delete_all_layers)
        self.view.widget_closed.connect(self.cleanup)
        self.view.search_text_changed.connect(self.view.filter_scene_tree)
        self.view.request_apply_aov_preset.connect(self.apply_aov_preset)
        self.view.selected_layers_changed.connect(self.update_layer_contents_view)

    def _setup_maya_callbacks(self):
        """Mayaシーンの変更を検知してUIを自動更新するコールバックを設定する。"""
        self.cleanup()
        
        dag_callback = om.MDGMessage.addNodeAddedCallback(self._on_scene_changed, "transform")
        self._callback_ids.append(dag_callback)
        node_removed_callback = om.MDGMessage.addNodeRemovedCallback(self._on_scene_changed, "transform")
        self._callback_ids.append(node_removed_callback)
        render_layer_callback = om.MEventMessage.addEventCallback("renderLayerManagerChange", self._on_render_setup_changed)
        self._callback_ids.append(render_layer_callback)
        scene_open_callback = om.MSceneMessage.addCallback(om.MSceneMessage.kAfterOpen, self._on_scene_changed)
        self._callback_ids.append(scene_open_callback)
        scene_new_callback = om.MSceneMessage.addCallback(om.MSceneMessage.kAfterNew, self._on_scene_changed)
        self._callback_ids.append(scene_new_callback)

    def _on_scene_changed(self, *args, **kwargs):
        print("Scene changed, refreshing UI...")
        self.populate_scene_tree()
        
    def _on_render_setup_changed(self, *args, **kwargs):
        print("Render Setup changed, refreshing layer list...")
        self.refresh_render_layer_list()

    def populate_scene_tree(self):
        try:
            hierarchy = scene_query.get_scene_hierarchy()
            self.view.populate_scene_tree_hierarchy(hierarchy)
            selected_paths = scene_query.get_selected_paths()
            self.view.sync_tree_selection(selected_paths)
            self.view.set_status("シーンツリーを更新しました。")
        except Exception as e:
            self.view.set_status(f"シーンツリーの更新に失敗: {e}", color="#FF6B6B")

    def _add_selected_to_list(self, list_name):
        selected_paths = [item.data(0, QtCore.Qt.UserRole) for item in self.view.scene_objects_tree.selectedItems()]
        if not selected_paths:
            selected_paths = scene_query.get_selected_paths()

        expand = self.view.expand_groups_radio.isChecked()
        resolved_paths = scene_query.resolve_selection(selected_paths, expand_groups=expand)
        
        target_widget = self.view.target_list_widget if list_name == 'target' else self.view.pvoff_list_widget
        other_widget = self.view.pvoff_list_widget if list_name == 'target' else self.view.target_list_widget
        
        other_list_items = {other_widget.item(i).text() for i in range(other_widget.count())}
        current_list_items = {target_widget.item(i).text() for i in range(target_widget.count())}

        for path in resolved_paths:
            if path in other_list_items:
                for i in range(other_widget.count()):
                    if other_widget.item(i).text() == path:
                        other_widget.takeItem(i)
                        break
            if path not in current_list_items:
                target_widget.addItem(path)
        
        self.view.set_status(f"{len(resolved_paths)}個のオブジェクトをリストに追加しました。")

    def _remove_selected_from_list(self, list_name):
        list_widget = self.view.target_list_widget if list_name == 'target' else self.view.pvoff_list_widget
        for item in list_widget.selectedItems():
            list_widget.takeItem(list_widget.row(item))
        self.view.set_status("選択したオブジェクトをリストから削除しました。")

    def create_render_layer(self):
        """Viewから設定を取得し、レンダーレイヤーを作成する。"""
        base_name = self.view.layer_name_le.text()
        
        target_list = [self.view.target_list_widget.item(i).text() for i in range(self.view.target_list_widget.count())]
        pvoff_list = [self.view.pvoff_list_widget.item(i).text() for i in range(self.view.pvoff_list_widget.count())]

        if not target_list and not pvoff_list:
            self.view.set_status("対象リストまたはPV OFFリストにオブジェクトを追加してください。", color="#FFD16B")
            return
            
        settings = {
            'create_each': self.view.create_each_checkbox.isChecked(),
            'aov_settings': self.view.get_aov_settings()
        }

        try:
            cmds.undoInfo(openChunk=True)
            # 【ロジック変更】Modelに全ての情報を渡し、レイヤー作成を依頼する
            created_count = self.model.create_layers_from_lists(
                base_name=base_name,
                target_list=target_list,
                pvoff_list=pvoff_list,
                settings=settings
            )
            if created_count > 0:
                self.view.set_status(f"{created_count}個のレンダーレイヤーを作成しました。", color="#7EE081")
                self.refresh_render_layer_list()
            else:
                 self.view.set_status("レンダーレイヤーは作成されませんでした。", color="#FFD16B")
        except ValueError as ve:
             self.view.set_status(f"エラー: {ve}", color="#FF6B6B")
        except Exception as e:
            self.view.set_status(f"レイヤー作成中にエラーが発生: {e}", color="#FF6B6B")
            import traceback
            traceback.print_exc()
        finally:
            cmds.undoInfo(closeChunk=True)

    def refresh_render_layer_list(self):
        layers = self.model.list_render_layers()
        self.view.populate_render_layer_list(layers)
        self.view.set_status("レンダーレイヤーリストを更新しました。")
        self.update_layer_contents_view([])

    def delete_selected_layers(self):
        selected_items = self.view.layer_list_widget.selectedItems()
        if not selected_items:
            self.view.set_status("削除するレイヤーを選択してください。", color="#FFD16B")
            return
            
        layer_names = [item.text() for item in selected_items]
        
        reply = self._confirm_dialog(
            "レイヤーの削除",
            f"以下の{len(layer_names)}個のレイヤーを削除しますか？\n\n- " + "\n- ".join(layer_names)
        )
        if not reply: return

        try:
            cmds.undoInfo(openChunk=True)
            deleted_count = self.model.delete_multiple_layers(layer_names)
            self.view.set_status(f"{deleted_count}個のレイヤーを削除しました。")
            self.refresh_render_layer_list()
        except Exception as e:
             self.view.set_status(f"削除中にエラー: {e}", color="#FF6B6B")
        finally:
            cmds.undoInfo(closeChunk=True)

    def delete_all_layers(self):
        all_layers = self.model.list_render_layers()
        if not all_layers:
            self.view.set_status("削除するレンダーレイヤーがありません。", color="#FFD16B")
            return
            
        reply = self._confirm_dialog(
            "全てのレイヤーを削除",
            f"シーン内の{len(all_layers)}個全てのレンダーレイヤーを削除しますか？\nこの操作は元に戻せません。",
            is_warning=True
        )
        if not reply: return

        try:
            cmds.undoInfo(openChunk=True)
            deleted_count = self.model.delete_multiple_layers(all_layers)
            self.view.set_status(f"{deleted_count}個のレイヤーを全て削除しました。")
            self.refresh_render_layer_list()
        except Exception as e:
            self.view.set_status(f"全削除中にエラー: {e}", color="#FF6B6B")
        finally:
            cmds.undoInfo(closeChunk=True)

    def apply_aov_preset(self, preset_name):
        aov_list = self.model.get_aov_preset(preset_name)
        self.view.set_aov_checkboxes(aov_list)
        self.view.set_status(f"AOVプリセット '{preset_name}' を適用しました。")

    def update_layer_contents_view(self, selected_layer_names):
        if not selected_layer_names:
            self.view.populate_layer_contents_tree(None)
            return

        try:
            layer_name = selected_layer_names[0]
            contents = self.model.get_layer_contents(layer_name)
            self.view.populate_layer_contents_tree(contents)
            self.view.set_status(f"レイヤー '{layer_name}' の内容を表示しました。")
        except Exception as e:
            self.view.set_status(f"レイヤー内容の取得エラー: {e}", color="#FF6B6B")
            self.view.populate_layer_contents_tree(None)

    def _confirm_dialog(self, title, message, is_warning=False):
        msg_box = QtWidgets.QMessageBox(self.view)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        msg_box.setStandardButtons(QtWidgets.QMessageBox.Ok | QtWidgets.QMessageBox.Cancel)
        msg_box.setDefaultButton(QtWidgets.QMessageBox.Cancel)
        if is_warning:
            msg_box.setIcon(QtWidgets.QMessageBox.Warning)
        else:
            msg_box.setIcon(QtWidgets.QMessageBox.Question)
        
        return msg_box.exec() == QtWidgets.QMessageBox.Ok