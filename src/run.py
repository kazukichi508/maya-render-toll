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
# 相対インポートから絶対インポートに変更
import view
import model
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

        # 各モジュールをリロード
        importlib.reload(model)
        importlib.reload(view)
        importlib.reload(controller)
        
        app_model = model.RenderLayerModel()
        app_view = view.RenderLayerToolView(parent=main_window)
        app_view.setObjectName(TOOL_OBJECT_NAME)

        app_controller = controller.RenderLayerController(model=app_model, view=app_view)
        app_view.controller = app_controller
        _tool_instance = app_controller

        app_view.show()
        print("Render Layer Tool (Rebuilt) started successfully.")

    except Exception as e:
        error_message = f"ツールの起動に失敗しました: {e}"
        print("-------------------- ERROR --------------------")
        traceback.print_exc()
        print("---------------------------------------------")
        cmds.warning(error_message)

if __name__ == "__main__":
    run()