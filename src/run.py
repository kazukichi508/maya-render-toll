# render_layer_tool/run.py
# -*- coding: utf-8 -*-
"""
ツールの起動、およびMVCコンポーネントの初期化と接続を行います。
"""
import importlib
import traceback
import maya.cmds as cmds

from PySide6 import QtWidgets
from shiboken6 import wrapInstance
from maya import OpenMayaUI as omui

# --- 修正箇所 ---
# モジュールのインポート順を整理
import scene_query
import model
import view
import controller
# ----------------

TOOL_OBJECT_NAME = "RenderLayerTool_MainInstance_v2"

_tool_instance = None

def get_maya_main_window():
    """Mayaのメインウィンドウオブジェクトを取得します。"""
    main_window_ptr = omui.MQtUtil.mainWindow()
    if main_window_ptr:
        return wrapInstance(int(main_window_ptr), QtWidgets.QWidget)
    return None

def run():
    """
    ツールを起動します。
    """
    global _tool_instance

    try:
        main_window = get_maya_main_window()
        if not main_window:
            raise RuntimeError("Mayaのメインウィンドウが見つかりません。GUIモードで実行してください。")
        
        for child in main_window.findChildren(QtWidgets.QWidget, TOOL_OBJECT_NAME):
            try:
                if hasattr(child, 'controller') and hasattr(child.controller, 'cleanup'):
                    child.controller.cleanup()
                child.close()
                child.deleteLater()
                print("既存のツールウィンドウをクローズしました。")
            except Exception as e:
                print(f"既存ウィンドウのクローズに失敗しました: {e}")

        # 各モジュールをリロード (依存関係の末端から)
        importlib.reload(scene_query)
        importlib.reload(model)
        importlib.reload(view)
        importlib.reload(controller)
        
        # --- ここから修正箇所 ---
        # 実際のファイル構成に合わせてインスタンス化処理を修正
        
        # View(UI)のインスタンスを作成
        app_view = view.RenderLayerToolView(parent=main_window)
        app_view.setObjectName(TOOL_OBJECT_NAME)

        # ControllerにViewを渡してインスタンスを作成
        app_controller = controller.RenderLayerToolController(view_instance=app_view)
        
        # ViewからControllerにアクセスできるように参照を保持
        app_view.controller = app_controller
        _tool_instance = app_controller

        # UIを表示
        app_view.show()
        print("Render Layer Tool (Rebuilt) started successfully.")
        # --- 修正箇所ここまで ---

    except Exception as e:
        error_message = f"ツールの起動に失敗しました: {e}"
        print("-------------------- ERROR --------------------")
        traceback.print_exc()
        print("---------------------------------------------")
        cmds.warning(error_message)

if __name__ == "__main__":
    run()
