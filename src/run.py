# -*- coding: utf-8 -*-
# render_layer_tool/run.py

from PySide6 import QtWidgets
from shiboken6 import wrapInstance

from maya import OpenMayaUI as omui

# --- 修正: 相対インポートから直接インポートに変更 ---
import model
import view
import controller

TOOL_OBJECT_NAME = "MyRenderLayerTool_MainInstance"

def _maya_main_window():
    ptr = omui.MQtUtil.mainWindow()
    if not ptr:
        return None
    return wrapInstance(int(ptr), QtWidgets.QWidget)

def run():
    """ツールを起動（ホットリロード対応）"""
    
    main_window = _maya_main_window()
    existing_window = main_window.findChild(QtWidgets.QWidget, TOOL_OBJECT_NAME)
    if existing_window:
        try:
            # クリーンアップ関数を呼び出す
            if hasattr(existing_window, '_controller') and existing_window._controller:
                existing_window._controller.cleanup()
            existing_window.close()
            existing_window.deleteLater()
        except Exception as e:
            print(f"[RenderLayerTool] Failed to close existing window: {e}")

    # --- インスタンスの作成と接続 ---
    app_view = view.RenderLayerToolView(parent=main_window)
    app_view.setObjectName(TOOL_OBJECT_NAME)
    
    app_controller = controller.RenderLayerToolController(view_instance=app_view)
    
    # ウィンドウにコントローラーへの参照を保持させる
    app_view._controller = app_controller

    app_controller.show()
    
    print("[RenderLayerTool] Tool started successfully.")

