# -*- coding: utf-8 -*-
import sys
import os
import importlib
import traceback

# --- ▼▼▼【修正点】アンロード処理をここに統合 ▼▼▼ ---
def unload_previous_modules():
    """
    Mayaのセッションからこのツールに関連する古いモジュールをすべて削除する。
    これにより、Mayaを再起動せずにコードの変更を確実に反映させる。
    """
    modules_to_unload = [
        'run',
        'controller',
        'view',
        'model',
        'layers',
        'visibility',
        'scene_query',
        'aov',
        'rs_utils'
    ]
    
    unloaded_count = 0
    for module_name in modules_to_unload:
        if module_name in sys.modules:
            try:
                del sys.modules[module_name]
                unloaded_count += 1
            except Exception:
                # アンロード中のエラーは無視
                pass
    
    if unloaded_count > 0:
        print(f"古いツールモジュールを {unloaded_count} 件アンロードしました。")
# --- ▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲ ---

try:
    # 1. まず、古いモジュールをアンロードする
    unload_previous_modules()

    # 2. このスクリプトのパスを特定し、Pythonの検索パスに追加する
    tool_path = os.path.dirname(os.path.abspath(__file__))
    if tool_path not in sys.path:
        sys.path.append(tool_path)

    # 3. モジュールを（再）インポートする
    #    アンロードされたため、importlib.reloadだけでなく、import文自体も必要です。
    import rs_utils
    import scene_query
    import visibility
    import aov
    import layers
    import model
    import view
    import controller
    import run

    # 4. 念のため各モジュールをリロードする
    importlib.reload(rs_utils)
    importlib.reload(scene_query)
    importlib.reload(visibility)
    importlib.reload(aov)
    importlib.reload(layers)
    importlib.reload(model)
    importlib.reload(view)
    importlib.reload(controller)
    importlib.reload(run)

    # 5. メインの起動関数を実行する
    run.run()

    print(f"ツールを再ロードして起動しました: {tool_path}")

except NameError:
    print("【エラー】このスクリプトはファイルとして保存し、Mayaにドラッグ＆ドロップするか、")
    print("スクリプトエディタの「ファイル > スクリプトのロード」から実行してください。")
    print("エディタに直接コードを貼り付けて実行すると、相対パスを認識できません。")
except Exception as e:
    print(f"【エラー】ツールの起動中に予期せぬ問題が発生しました: {e}")
    traceback.print_exc()

