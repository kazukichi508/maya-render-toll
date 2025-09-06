# render_layer_tool/run.py
# -*- coding: utf-8 -*-
"""
ツールの起動、およびMVCコンポーネントの初期化と接続を行います。
"""
import traceback
import maya.cmds as cmds

from PySide6 import QtWidgets
from shiboken6 import wrapInstance
from maya import OpenMayaUI as omui

# 必要なモジュールをインポート
import view
import model
import controller
import scene_query

TOOL_OBJECT_NAME = "RenderLayerTool_MainInstance_v3"

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

        # 【修正】古いインスタンスが残っている場合、UI検索だけでなく
        # グローバル変数からも直接クリーンアップを実行し、参照を解除する
        if _tool_instance:
            try:
                _tool_instance.cleanup()
                print("前回のツールのクリーンアップ処理を実行しました。")
            except Exception as e:
                print(f"既存インスタンスのクリーンアップに失敗: {e}")
            finally:
                # _tool_instanceの参照を確実に解除する
                _tool_instance = None
        
        # 既存のウィンドウを名前で検索して閉じる (この処理も維持)
        for child in main_window.findChildren(QtWidgets.QWidget, TOOL_OBJECT_NAME):
            try:
                # こちらのクリーンアップも念のため実行
                if hasattr(child, 'controller') and child.controller:
                    child.controller.cleanup()
                child.close()
                child.deleteLater()
                print("既存のツールウィンドウをクローズしました。")
            except Exception as e:
                print(f"既存ウィンドウのクローズに失敗しました: {e}")
        
        # ViewとControllerをインスタンス化して接続
        app_view = view.RenderLayerToolView(parent=main_window)
        app_view.setObjectName(TOOL_OBJECT_NAME)
        
        # ControllerにViewのインスタンスを渡す
        app_controller = controller.RenderLayerToolController(view_instance=app_view)
        
        # ViewからControllerにアクセスできるように参照を保持
        app_view.controller = app_controller
        # グローバル変数に新しいインスタンスを格納
        _tool_instance = app_controller

        app_view.show()

    except Exception as e:
        error_message = f"ツールの起動に失敗しました: {e}"
        print("-------------------- ERROR --------------------")
        traceback.print_exc()
        print("---------------------------------------------")
        cmds.warning(error_message)

if __name__ == "__main__":
    run()