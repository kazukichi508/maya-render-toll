# render_layer_tool/controller.py
# -*- coding: utf-8 -*-
import maya.cmds as cmds
import maya.OpenMaya as om # Maya Callback用 (OpenMaya 1.0)
import maya.utils as cmds_utils # executeDeferred用
import logging
import traceback
from PySide6 import QtCore, QtWidgets

# 依存モジュールのインポート
import model
import scene_query

# Render Setup API (コールバック解除用)
try:
    import maya.app.renderSetup.model.renderSetup as rs
except ImportError:
    rs = None

class RenderLayerToolController(QtCore.QObject):
    """
    ViewとModel間のインタラクションを制御し、シーンの変更を監視します。
    """
    def __init__(self, view_instance):
        super(RenderLayerToolController, self).__init__()
        self.view = view_instance
        
        try:
            self.model = model.RenderLayerManager()
        except EnvironmentError as e:
            self.view.set_status(f"初期化失敗: {e}", color="#E57373")
            self.model = None
            return
        
        self.callbacks = []
        self.structure_change_timer = QtCore.QTimer()
        self.structure_change_timer.setSingleShot(True)
        self.structure_change_timer.setInterval(500) # 500ms遅延
        
        # Observer管理用フラグ。Trueの間はObserverが反応しない。
        self.is_processing_layers = False 
        # 【エラー修正】Undoチャンク状態管理フラグ
        self.undo_chunk_open = False
        
        self._connect_signals()
        self._register_callbacks()
        self._initialize_ui()

    # (中略: _connect_signals, _initialize_ui, _register_callbacks, cleanup, Callback Handlers は変更なし)

    def _connect_signals(self):
        v = self.view
        v.request_populate_tree.connect(self.populate_scene_tree)
        v.search_text_changed.connect(self.view.filter_scene_tree)
        self.structure_change_timer.timeout.connect(self.populate_scene_tree)
        v.request_add_to_target.connect(self.add_to_target_list)
        v.request_remove_from_target.connect(self.remove_from_target_list)
        v.request_create_layer.connect(self.handle_create_layer)
        v.request_layer_list_refresh.connect(self.refresh_render_layer_list)
        v.request_delete_selected_layers.connect(self.handle_delete_selected_layers)
        v.request_delete_all_layers.connect(self.handle_delete_all_layers)
        v.request_apply_aov_preset.connect(self._apply_aov_preset)
        v.widget_closed.connect(self.cleanup)

    def _initialize_ui(self):
        self.populate_scene_tree()
        self.refresh_render_layer_list()
        self._apply_aov_preset("Basic")
        self.view.set_status("準備完了。")

    def _register_callbacks(self):
        try:
            cb_id = om.MEventMessage.addEventCallback("SelectionChanged", self._on_selection_changed)
            self.callbacks.append(cb_id)
            cb_id = om.MEventMessage.addEventCallback("DagObjectCreated", lambda *args: self.structure_change_timer.start())
            self.callbacks.append(cb_id)
            cb_id = om.MEventMessage.addEventCallback("NameChanged", lambda *args: self.structure_change_timer.start())
            self.callbacks.append(cb_id)
            if rs:
                obs_added = rs.addRenderSetupObserver(rs.kLayerAdded, self._on_render_setup_changed)
                self.callbacks.append((rs.kLayerAdded, obs_added))
                obs_removed = rs.addRenderSetupObserver(rs.kLayerRemoved, self._on_render_setup_changed)
                self.callbacks.append((rs.kLayerRemoved, obs_removed))
        except Exception as e:
            logging.error(f"コールバックの登録に失敗しました: {e}")

    def cleanup(self):
        if self.callbacks:
            for cb_info in self.callbacks:
                try:
                    if isinstance(cb_info, (int, om.MCallbackId)):
                         om.MMessage.removeCallback(cb_info)
                    elif rs and isinstance(cb_info, tuple) and len(cb_info) == 2:
                         rs.removeRenderSetupObserver(cb_info[0], cb_info[1])
                except RuntimeError:
                    pass
            self.callbacks = []

    def _on_selection_changed(self, *args):
        selected_paths = scene_query.get_selected_paths()
        QtCore.QTimer.singleShot(0, lambda: self.view.sync_tree_selection(selected_paths))

    def _on_render_setup_changed(self, *args):
        if self.is_processing_layers:
            return
        QtCore.QTimer.singleShot(200, self.refresh_render_layer_list)

    # --- Render Layer Operations (レイヤー作成・削除) ---

    def handle_create_layer(self):
        if not self.model: return
        self.view.set_status("レイヤー作成を開始しています...")
        cmds_utils.executeDeferred(self._execute_create_layer)

    def _execute_create_layer(self):
        """レイヤー作成の実行処理。(Undo対応・安定化)"""
        if self.is_processing_layers:
             self.view.set_status("エラー: 別のレイヤー操作が実行中です。", "#E57373")
             return

        # Viewから現在の設定を取得
        layer_name_input = self.view.layer_name_le.text().strip()
        settings = {
            'auto_matte': self.view.auto_matte_checkbox.isChecked(),
            'create_each': self.view.create_each_checkbox.isChecked(),
            'aov_settings': self.view.get_aov_settings()
        }
        target_objects = self._get_objects_from_list(self.view.target_list_widget)
        pvoff_objects = self._get_objects_from_list(self.view.pvoff_list_widget)

        if not target_objects and not pvoff_objects:
            self.view.set_status("エラー: リストに有効なオブジェクトがありません。", "#E57373")
            return

        # レイヤー作成実行 (Undoチャンク開始)
        # 【エラー修正】フラグ管理を使用して安全に開く
        self._safe_open_chunk("Create Render Layers")
        
        success = False
        
        # Observerを一時停止
        self.is_processing_layers = True
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        
        try:
            self.view.set_status("レイヤー作成中... (Render Setup API実行中)")

            # Modelに作成を依頼
            created_count = self.model.create_render_layers(
                layer_name_input, target_objects, pvoff_objects, settings
            )
            
            # 結果報告
            if created_count > 0:
                self.view.set_status(f"成功: {created_count} 個のレンダーレイヤーを作成しました。（重複名は自動連番）", "#7EE081")
                success = True
            else:
                 self.view.set_status("情報: レイヤーは作成されませんでした（詳細はスクリプトエディタ参照）。", "#FFB74D")

        except ValueError as e:
            self.view.set_status(f"入力エラー: {e}", "#E57373")
            self._safe_undo()
        except Exception as e:
            self.view.set_status(f"致命的なエラーが発生しました: {e}", "#E57373")
            traceback.print_exc()
            self._safe_undo()
        finally:
            # Undoチャンクを安全に閉じる
            self._safe_close_chunk()
            QtWidgets.QApplication.restoreOverrideCursor()
            self.is_processing_layers = False

        if success:
            QtCore.QTimer.singleShot(50, self.refresh_render_layer_list)

    def refresh_render_layer_list(self):
        # (変更なし)
        if not self.model: return
        try:
            self.view.layer_list_widget.blockSignals(True)
            layer_names = self.model.list_render_layers()
            self.view.populate_render_layer_list(layer_names)
        except Exception as e:
            logging.error(f"レイヤーリスト更新エラー: {e}")
        finally:
            try:
                if self.view.layer_list_widget:
                     self.view.layer_list_widget.blockSignals(False)
            except RuntimeError:
                pass

    def handle_delete_selected_layers(self):
        # (変更なし)
        if not self.model: return
        selected_items = self.view.layer_list_widget.selectedItems()
        if not selected_items:
            self.view.set_status("削除するレイヤーを選択してください。", "#FFB74D")
            return

        layer_names = [item.text() for item in selected_items]
        reply = QtWidgets.QMessageBox.question(self.view, '確認',
                                               f"選択した {len(layer_names)} 個のレイヤーを削除しますか？",
                                               QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                                               QtWidgets.QMessageBox.No)

        if reply == QtWidgets.QMessageBox.Yes:
            self.view.set_status("レイヤー削除を開始しています...")
            cmds_utils.executeDeferred(lambda: self._execute_delete_layers(layer_names))

    def handle_delete_all_layers(self):
        # (変更なし)
        if not self.model: return
        layer_names = self.model.list_render_layers()
        if not layer_names:
            self.view.set_status("削除するレイヤーがありません。")
            return

        reply = QtWidgets.QMessageBox.warning(self.view, '警告',
                                               "全てのレンダーレイヤー（Master Layer以外）を削除します。よろしいですか？",
                                               QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                                               QtWidgets.QMessageBox.No)

        if reply == QtWidgets.QMessageBox.Yes:
            self.view.set_status("全レイヤー削除を開始しています...")
            cmds_utils.executeDeferred(lambda: self._execute_delete_layers(layer_names))

    def _execute_delete_layers(self, layer_names):
        """レイヤー削除の実行処理 (Undo対応・安定化)"""
        if self.is_processing_layers:
             self.view.set_status("エラー: 別のレイヤー操作が実行中です。", "#E57373")
             return
             
        # Undoチャンク開始
        # 【エラー修正】フラグ管理を使用して安全に開く
        self._safe_open_chunk("Delete Render Layers")
        
        success = False
        
        # Observerを一時停止
        self.is_processing_layers = True
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        
        try:
            self.view.set_status("レイヤー削除中... (Render Setup API実行中)")
            deleted_count = self.model.delete_multiple_layers(layer_names)
            
            if deleted_count > 0:
                success = True

            if deleted_count == len(layer_names):
                self.view.set_status(f"{deleted_count}個のレイヤーを削除しました。", "#7EE081")
            else:
                self.view.set_status(f"{len(layer_names)}個中{deleted_count}個のレイヤーを削除しました。一部失敗しました。", "#FFB74D")

        except Exception as e:
            self.view.set_status(f"削除エラー: {e}", "#E57373")
            self._safe_undo()
        finally:
            # Undoチャンクを安全に閉じる
            self._safe_close_chunk()
            QtWidgets.QApplication.restoreOverrideCursor()
            self.is_processing_layers = False
        
        if success:
            QtCore.QTimer.singleShot(50, self.refresh_render_layer_list)

    # --- Undo Helpers (修正箇所) ---
    
    def _safe_open_chunk(self, chunk_name):
        """Undoチャンクを安全に開く。"""
        if self.undo_chunk_open:
             logging.warning("Attempted to open a new Undo chunk while one is already open. Closing previous one.")
             self._safe_close_chunk()
        cmds.undoInfo(openChunk=True, chunkName=chunk_name)
        self.undo_chunk_open = True

    def _safe_undo(self):
        """Undoチャンクを安全に閉じてからUndoを実行する。"""
        self._safe_close_chunk()
        try:
            # Undoが有効な場合のみ実行
            if cmds.undoInfo(q=True, state=True):
                cmds.undo()
        except Exception as e:
            logging.error(f"Undo操作に失敗しました: {e}")

    def _safe_close_chunk(self):
        """Undoチャンクが開いている場合のみ閉じる。(フラグ管理版)"""
        # cmds.undoInfo(query=True) を使わず、Python側のフラグで管理する
        if self.undo_chunk_open:
            try:
                cmds.undoInfo(closeChunk=True)
            except Exception as e:
                 logging.error(f"Undoチャンクのクローズに失敗しました: {e}")
            finally:
                # 成功・失敗に関わらずフラグは下ろす
                self.undo_chunk_open = False

    # --- AOV Management & List Management (変更なし・参考用に再掲) ---
    
    def _apply_aov_preset(self, preset_name):
        if not self.model: return
        target_aovs = self.model.get_aov_preset(preset_name)
        self.view.set_aov_checkboxes(target_aovs)
        self.view.set_status(f"AOVプリセット '{preset_name}' を適用しました。")
    
    def populate_scene_tree(self):
        try:
            hierarchy_data = scene_query.get_scene_hierarchy()
            self.view.populate_scene_tree_hierarchy(hierarchy_data)
            current_filter = self.view.search_le.text()
            if current_filter:
                self.view.filter_scene_tree(current_filter)
            self._on_selection_changed()
        except Exception as e:
            self.view.set_status(f"ツリー更新エラー: {e}", color="#E57373")
            traceback.print_exc()

    def _get_list_widgets(self, list_name):
        if list_name == 'target':
            return self.view.target_list_widget, self.view.pvoff_list_widget
        else:
            return self.view.pvoff_list_widget, self.view.target_list_widget

    def add_to_target_list(self, list_name):
        target_list_widget, other_list_widget = self._get_list_widgets(list_name)
        selected_items = self.view.scene_objects_tree.selectedItems()
        paths_to_add = [item.data(0, QtCore.Qt.UserRole) for item in selected_items if item.data(0, QtCore.Qt.UserRole)]
        
        if not paths_to_add: return
        
        expand_groups = self.view.expand_groups_radio.isChecked()
        final_paths = scene_query.resolve_selection(paths_to_add, expand_groups)

        if not final_paths:
            self.view.set_status("選択範囲に有効なオブジェクトが見つかりません。", color="#FFB74D")
            return

        added_count = 0; moved_count = 0
        current_target_paths = {target_list_widget.item(i).data(QtCore.Qt.UserRole) for i in range(target_list_widget.count())}

        for path in final_paths:
            short_name = path.split('|')[-1]
            if path not in current_target_paths:
                is_moved = False
                for i in range(other_list_widget.count() -1, -1, -1):
                    if other_list_widget.item(i).data(QtCore.Qt.UserRole) == path:
                        other_list_widget.takeItem(i)
                        is_moved = True; moved_count += 1
                        break
                
                item = QtWidgets.QListWidgetItem(short_name)
                item.setData(QtCore.Qt.UserRole, path)
                target_list_widget.addItem(item)
                current_target_paths.add(path)

                if not is_moved: added_count += 1

        status_msg = f"{list_name.upper()}リスト更新: "
        if added_count > 0: status_msg += f"{added_count}件追加"
        if moved_count > 0:
            if added_count > 0: status_msg += ", "
            status_msg += f"{moved_count}件移動"
        if added_count == 0 and moved_count == 0: status_msg = "リストは最新です。"
        self.view.set_status(status_msg)

    def remove_from_target_list(self, list_name):
        target_list_widget, _ = self._get_list_widgets(list_name)
        selected_items = target_list_widget.selectedItems()
        if not selected_items: return
        for item in selected_items:
            target_list_widget.takeItem(target_list_widget.row(item))
        self.view.set_status(f"{len(selected_items)}個のアイテムを{list_name.upper()}リストから削除しました。")

    def _get_objects_from_list(self, list_widget):
        objects = []
        for i in range(list_widget.count()):
            path = list_widget.item(i).data(QtCore.Qt.UserRole)
            if path and cmds.objExists(path):
                objects.append(path)
        return objects