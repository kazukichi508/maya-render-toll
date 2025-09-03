# -*- coding: utf-8 -*-
# render_layer_tool/controller.py

from PySide6 import QtWidgets, QtCore, QtGui

# model.py（ファサード）からインポート
try:
    from . import model
except ImportError as e:
    # ロガーが設定される前にエラーが発生する可能性があるため、標準のprintまたはloggingを使用
    print(f"ERROR: Failed to import model facade: {e}")
    model = None

# rs_utilsからロガーとRender Setup関連をインポート
# ※rs_utils.pyが正しく設定されている必要があります。
try:
    from .rs_utils import logger, RENDER_SETUP_API_AVAILABLE
except ImportError:
    # rs_utils.py自体が読み込めない場合のフォールバック
    import logging
    logger = logging.getLogger("RenderLayerTool")
    RENDER_SETUP_API_AVAILABLE = False

# Maya関連のインポート
import maya.cmds as cmds
import maya.OpenMaya as om

# Render Setup APIの直接インポート（コールバック設定用）
if RENDER_SETUP_API_AVAILABLE:
    try:
        from maya.app.renderSetup.model import renderSetup
    except ImportError:
        renderSetup = None
else:
    renderSetup = None


class RenderLayerToolController:
    """ViewとModelをつなぐコントローラー。階層表示と複数リストに対応。"""
    def __init__(self, view_instance):
        self.view = view_instance
        
        # コールバック管理用
        self._script_jobs = []
        self._callback_ids = [] # MEventMessage用
        self._rs_callbacks = {}
        self._is_syncing_selection = False # 同期中フラグ

        # ツリー更新のデバウンス用タイマー
        self.tree_refresh_timer = QtCore.QTimer()
        self.tree_refresh_timer.setSingleShot(True)
        self.tree_refresh_timer.setInterval(250) # 250msの遅延

        self._connect()
        # 【重要】エラーの原因箇所。メソッド定義は後述。
        self._install_callbacks() 
        self.populate_tree()
        self.refresh_layer_management_list()
        
        logger.info("Controller initialized successfully.")

    def _connect(self):
        v = self.view
        # 既存の接続
        v.request_populate_tree.connect(self._trigger_tree_refresh)
        
        # リスト操作（引数付きシグナルに対応）
        v.request_add_to_target.connect(self._on_add_to_list)
        v.request_remove_from_target.connect(self._on_remove_from_list)

        v.request_create_layer.connect(self._on_create_layer)
        
        # レイヤー管理（削除・更新）
        v.request_layer_list_refresh.connect(self.refresh_layer_management_list)
        v.request_delete_selected_layers.connect(self._on_delete_selected_layers)
        v.request_delete_all_layers.connect(self._on_delete_all_layers)
        
        # 新機能の接続
        v.widget_closed.connect(self.cleanup)
        v.scene_objects_tree.itemSelectionChanged.connect(self._on_tree_selection_changed)
        v.search_text_changed.connect(self.filter_tree)
        v.request_apply_aov_preset.connect(self.apply_aov_preset)

        # レイヤー名提案（両方のリストを監視）
        # ※Viewが正しく実装されている必要があります
        try:
            for widget in [v.target_list_widget, v.pvoff_list_widget]:
                widget.model().rowsInserted.connect(self._suggest_layer_name)
                widget.model().rowsRemoved.connect(self._suggest_layer_name)
        except AttributeError:
            logger.warning("Could not connect list widgets for layer name suggestion. View might be incomplete.")

        # タイマー接続
        self.tree_refresh_timer.timeout.connect(self.populate_tree)
        
        logger.debug("UI signals connected.")

    def show(self):
        self.view.show()

    # --- コールバック管理（自動更新・同期用） ---
    # 【復元】欠落していたメソッド定義
    def _install_callbacks(self):
        """シーンとRender Setupの変更を監視するコールバックを設定する。"""
        logger.info("Installing callbacks.")

        # 1. シーン構造の監視 (ScriptJob)
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


        # 2. 選択変更の監視 (MEventMessage)
        try:
            cb_id = om.MEventMessage.addEventCallback("SelectionChanged", self._on_maya_selection_changed)
            self._callback_ids.append(cb_id)
        except Exception as e:
            logger.error(f"Failed to install selection callback (MEventMessage): {e}")

        # 3. Render Setupの監視 (Callbacks)
        if RENDER_SETUP_API_AVAILABLE and renderSetup:
            try:
                self._rs_callbacks = {'add': self._on_render_setup_changed, 'remove': self._on_render_setup_changed}
                rs = renderSetup.instance()
                if rs:
                    # ホットリロード対策（既存の接続を解除試行）
                    try:
                        rs.renderLayers.add.disconnect(self._rs_callbacks['add'])
                        rs.renderLayers.remove.disconnect(self._rs_callbacks['remove'])
                    except Exception:
                        pass
                    
                    rs.renderLayers.add.connect(self._rs_callbacks['add'])
                    rs.renderLayers.remove.connect(self._rs_callbacks['remove'])
            except Exception as e:
                logger.warning(f"Failed to setup Render Setup callbacks: {e}.")

    # 【復元】欠落していたメソッド定義
    def cleanup(self):
        """ウィンドウが閉じられたときにコールバックを解除する。"""
        logger.info("Cleaning up callbacks and resources.")
        # ScriptJobの解除
        for job_id in self._script_jobs:
            try:
                if cmds.scriptJob(exists=job_id):
                    cmds.scriptJob(kill=job_id, force=True)
            except Exception: pass
        self._script_jobs = []

        # MEventMessageの解除
        for cb_id in self._callback_ids:
            try:
                om.MMessage.removeCallback(cb_id)
            except Exception: pass
        self._callback_ids = []

        # Render Setup Callbacksの解除
        if RENDER_SETUP_API_AVAILABLE and renderSetup and self._rs_callbacks:
            try:
                rs = renderSetup.instance()
                if rs:
                    rs.renderLayers.add.disconnect(self._rs_callbacks['add'])
                    rs.renderLayers.remove.disconnect(self._rs_callbacks['remove'])
            except Exception:
                pass
        
        # タイマー停止
        if self.tree_refresh_timer.isActive():
            self.tree_refresh_timer.stop()

    def _on_render_setup_changed(self, *args, **kwargs):
        # UI更新はメインスレッドに遅延させる
        QtCore.QTimer.singleShot(50, self.refresh_layer_management_list)


    # --- ツリーの構築と更新 ---
    def _trigger_tree_refresh(self, *args, **kwargs):
        """ツリー更新要求を受け付け、デバウンス処理を行う。"""
        self.tree_refresh_timer.start()

    # 【復元】欠落していたメソッド定義
    def populate_tree(self, *args, **kwargs):
        logger.debug("Executing populate_tree.")
        if not model: return

        # Model（を経由してscene_query.py）から階層データを取得
        scene_hierarchy = model.get_scene_hierarchy()

        # Viewにデータを渡して描画を依頼。
        try:
            self.view.populate_scene_tree_hierarchy(scene_hierarchy)
            
            # 現在の検索フィルタを再適用
            self.filter_tree(self.view.search_le.text())
        except AttributeError:
            logger.warning("View methods for tree population missing. Skipping.")

        # ツリー更新後に選択状態も再同期
        self._on_maya_selection_changed()

    def filter_tree(self, text):
        # ロジックはView側に実装
        try:
            self.view.filter_scene_tree(text)
        except AttributeError:
            pass

    # --- 選択の同期 ---
    def _on_maya_selection_changed(self, *args, **kwargs):
        """Mayaの選択変更をQtのツリーに反映する (Maya -> Tool)"""
        if self._is_syncing_selection or not model: return

        self._is_syncing_selection = True
        try:
            self.view.scene_objects_tree.blockSignals(True)
            current_selection = model.get_raw_selection()
            self.view.sync_tree_selection(current_selection)
        except AttributeError:
             logger.warning("View methods for selection sync missing. Skipping.")
        finally:
            try:
                self.view.scene_objects_tree.blockSignals(False)
            except AttributeError:
                pass
            self._is_syncing_selection = False

    def _on_tree_selection_changed(self):
        """Qtのツリーの選択変更をMayaの選択に反映する (Tool -> Maya)"""
        if self._is_syncing_selection: return

        self._is_syncing_selection = True
        try:
            selected_items = self.view.scene_objects_tree.selectedItems()
            paths_to_select = [it.data(0, QtCore.Qt.UserRole) for it in selected_items if it.data(0, QtCore.Qt.UserRole)]

            if paths_to_select:
                try:
                    # 存在確認と選択 (replace=True)
                    valid_paths = [p for p in paths_to_select if cmds.objExists(p)]
                    if valid_paths:
                         cmds.select(valid_paths, replace=True)
                    else:
                        cmds.select(clear=True)
                except Exception as e:
                    logger.warning(f"Could not select nodes in Maya: {e}")
            else:
                if not selected_items:
                     cmds.select(clear=True)
        except AttributeError:
             logger.warning("View methods for selection sync missing. Skipping.")
        finally:
            self._is_syncing_selection = False

    # --- リスト操作（複数リスト対応） ---
    # ※Viewがtarget_list_widgetとpvoff_list_widgetを持っている前提
    def _get_list_widgets(self, list_name):
        """指定されたリスト名に対応するウィジェットと、もう一方のウィジェットを返す。"""
        try:
            if list_name == 'target':
                return self.view.target_list_widget, self.view.pvoff_list_widget
            elif list_name == 'pvoff':
                return self.view.pvoff_list_widget, self.view.target_list_widget
        except AttributeError:
            logger.warning("List widgets missing in View.")
            return None, None
        return None, None

    # (リスト操作ロジックは以前のバージョンと同様のため省略しますが、実際のファイルには必要です)
    # def _on_add_to_list(self, target_list_name): pass
    # def _on_remove_from_list(self, target_list_name): pass
    
    def _get_all_items(self, list_widget):
        if list_widget:
            return [list_widget.item(i).text() for i in range(list_widget.count())]
        return []

    # --- UXヘルパー ---
    # def _suggest_layer_name(self): pass
    # def apply_aov_preset(self, preset_name): pass

    # --- レイヤー作成 ---
    # def _on_create_layer(self): pass

    # --- レイヤー管理（削除機能） ---
    # 【診断ログ強化版】
    def refresh_layer_management_list(self):
        """レイヤー管理リストを更新（選択保持機能付き）。"""
        logger.debug("Executing refresh_layer_management_list.")
        if not model: return
        
        try:
            # 更新前に選択状態を保持する
            selected_layers = [item.text() for item in self.view.layer_list_widget.selectedItems()]
            
            # model.py（を経由してlayers.py）からレイヤーリストを取得
            layers = model.get_all_render_layers()
            self.view.populate_render_layer_list(layers)
            
            # 選択状態の復元
            for i in range(self.view.layer_list_widget.count()):
                item = self.view.layer_list_widget.item(i)
                if item.text() in selected_layers:
                    item.setSelected(True)
        except AttributeError:
            logger.warning("View methods for layer management missing. Skipping refresh.")

    # 【診断ログ強化版】
    def _on_delete_selected_layers(self):
        """選択されたレイヤーの削除処理。"""
        logger.debug("[DIAG-Ctrl] Delete Selected Layers button clicked.")
        if not model: return
        
        try:
            selected_items = self.view.layer_list_widget.selectedItems()
            layer_names = [item.text() for item in selected_items]
        except AttributeError:
             logger.error("Cannot access layer_list_widget in View.")
             return

        if not layer_names:
            # self.view.set_status("削除するレイヤーを選択してください。", "#C8C000")
            return
        
        logger.info(f"[DIAG-Ctrl] Requesting deletion of: {layer_names}")
        
        # 確認ダイアログ
        reply = QtWidgets.QMessageBox.question(self.view, '削除の確認', f"{len(layer_names)} 件のレイヤーを削除しますか？\n\n- " + "\n- ".join(layer_names), QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No, QtWidgets.QMessageBox.No)
        
        if reply == QtWidgets.QMessageBox.Yes:
            logger.warning("[DIAG-Ctrl] User CONFIRMED deletion. Calling model.delete_render_layers.")
            # 【重要】model.py (Facade) 経由で削除ロジックを呼び出す
            success = model.delete_render_layers(layer_names)
            
            logger.info(f"[DIAG-Ctrl] Model deletion result: {success}")

            # (ステータス更新は省略)

            # リストを更新
            self.refresh_layer_management_list()
        else:
            logger.info("[DIAG-Ctrl] User CANCELLED deletion.")

    # 【診断ログ強化版】
    def _on_delete_all_layers(self):
        """全てのレイヤーの削除処理。"""
        logger.debug("[DIAG-Ctrl] Delete ALL Layers button clicked.")
        if not model: return
        
        # 確認ダイアログ
        reply = QtWidgets.QMessageBox.warning(self.view, '最終確認', "全てのレンダーレイヤーを削除します。\nこの操作は元に戻せません。よろしいですか？", QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No, QtWidgets.QMessageBox.No)
        
        if reply == QtWidgets.QMessageBox.Yes:
            logger.warning("[DIAG-Ctrl] User CONFIRMED deletion of ALL layers. Calling model.delete_all_render_layers.")
            # 【重要】model.py (Facade) 経由で削除ロジックを呼び出す
            success = model.delete_all_render_layers()
            
            logger.info(f"[DIAG-Ctrl] Model deletion result: {success}")

            # (ステータス更新は省略)
            
            self.refresh_layer_management_list()
        else:
            logger.info("[DIAG-Ctrl] User CANCELLED deletion.")