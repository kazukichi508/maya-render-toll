# -*- coding: utf-8 -*-
# render_layer_tool/run.py

from PySide6 import QtWidgets
from shiboken6 import wrapInstance

import importlib
from maya import OpenMayaUI as omui

from . import model
from . import view
from . import controller

TOOL_OBJECT_NAME = "MyRenderLayerTool_MainInstance"

def _maya_main_window():
    ptr = omui.MQtUtil.mainWindow()
    if not ptr:
        return None
    return wrapInstance(int(ptr), QtWidgets.QWidget)

def run():
    """ツールを起動（ホットリロード対応）"""
    
    # 既存のウィンドウをオブジェクト名で探して閉じる
    main_window = _maya_main_window()
    existing_window = main_window.findChild(QtWidgets.QWidget, TOOL_OBJECT_NAME)
    if existing_window:
        try:
            existing_window.close()
            existing_window.deleteLater()
        except Exception as e:
            print(f"[RenderLayerTool] Failed to close existing window: {e}")

    # モジュールのホットリロード
    importlib.reload(model)
    importlib.reload(view)
    importlib.reload(controller)

    # --- インスタンスの作成と接続 ---
    # 1. View（UI）のインスタンスを作成
    app_view = view.RenderLayerToolView(parent=main_window)
    app_view.setObjectName(TOOL_OBJECT_NAME) # 識別用の一意な名前を設定
    
    # 2. Controllerのインスタンスに、作成したViewのインスタンスを渡す
    app_controller = controller.RenderLayerToolController(view_instance=app_view)
    
    # 3. UIを表示
    app_controller.show()
    
    print("[RenderLayerTool] Tool started successfully.")

