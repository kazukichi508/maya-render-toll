# Maya 2025 / Arnold
# Render Setup レイヤー作成 → コレクション作成 → AOVを一括作成 →
# 各 AOV ノードの enabled をレイヤーの "絶対オーバーライド" で ON
# * createAbsoluteOverride の 2引数版(nodeName, attrName) を優先
# * 互換のため 1引数版("node.attr")／finalize ルートへ自動フォールバック

import maya.cmds as cmds

# ===== 設定 =====
LAYER_NAME = "beauty"
AOV_LIST = [
    # ライティング分解
    "diffuse_direct", "diffuse_indirect",
    "specular_direct", "specular_indirect",
    "transmission_direct", "transmission_indirect",
    "sss_direct", "sss_indirect",
    "emission",
    # ユーティリティ
    "N", "Z",
    # Cryptomatte
    "crypto_asset", "crypto_material", "crypto_object",
]

# ===== ヘルパ =====
def _ensure_mtoa_loaded():
    """Arnoldプラグイン（mtoa）をロード。"""
    try:
        if not cmds.pluginInfo("mtoa", q=True, loaded=True):
            cmds.loadPlugin("mtoa", quiet=True)
    except Exception:
        # Renderer切替で自動ロードされることが多いのでスルー
        pass

def ensure_arnold():
    """Arnold を現在レンダラに設定し、必要ノードを用意。"""
    _ensure_mtoa_loaded()
    if not cmds.objExists("defaultArnoldRenderOptions"):
        cmds.setAttr("defaultRenderGlobals.currentRenderer", "arnold", type="string")
    if cmds.objExists("defaultArnoldDriver"):
        try:
            cmds.setAttr("defaultArnoldDriver.ai_translator", "exr", type="string")
        except Exception:
            pass

def get_rs():
    from maya.app.renderSetup.model import renderSetup
    return renderSetup.instance()

def get_or_create_layer(rs, name):
    for lyr in rs.getRenderLayers():
        if lyr.name() == name:
            return lyr
    return rs.createRenderLayer(name)

def create_collection(layer, base_name):
    return layer.createCollection("{}_COL".format(base_name))

def collect_current_selection(col):
    sel = col.getSelector()
    members = cmds.ls(sl=True, long=True) or []
    sel.setStaticSelection(members)

def safe_abs_override(col, node, attr, value):
    """
    絶対オーバーライドを "node, attr" で安全に作成。
    1) 2引数版 createAbsoluteOverride(node, attr)
    2) 1引数版 createAbsoluteOverride("node.attr")
    3) AbsOverride + finalize("node.attr")
    の順にフォールバック。
    """
    if not cmds.objExists(node) or not cmds.attributeQuery(attr, node=node, exists=True):
        print("[WARN] 見つからないためスキップ: {}.{}".format(node, attr))
        return None

    from maya.app.renderSetup.model import override as rs_override

    # 1) 2引数版
    try:
        ov = col.createAbsoluteOverride(node, attr)
        ov.setAttrValue(value)
        print("[OK] Override(2arg): {}.{} = {}".format(node, attr, value))
        return ov
    except TypeError:
        pass

    # 2) 1引数版
    node_attr = "{}.{}".format(node, attr)
    try:
        ov = col.createAbsoluteOverride(node_attr)
        ov.setAttrValue(value)
        print("[OK] Override(1arg): {} = {}".format(node_attr, value))
        return ov
    except TypeError:
        pass

    # 3) finalize ルート
    try:
        ov = col.createOverride("abs_{}_{}".format(node.replace("|", "_").replace(":", "_"), attr),
                                rs_override.AbsOverride.kTypeId)
        ov.finalize(node_attr)
        ov.setAttrValue(value)
        print("[OK] Override(finalize): {} = {}".format(node_attr, value))
        return ov
    except Exception as e:
        print("[ERR] すべてのルートで失敗: {}  -> {}".format(node_attr, e))
        return None

def ensure_aovs(aov_names):
    """指定 AOV を作成し、aiAOV_* ノード名のリストを返す。"""
    _ensure_mtoa_loaded()
    try:
        import mtoa.aovs as aovs
    except Exception as e:
        raise RuntimeError("Arnold(mtoa) がロードされていません。Arnold を有効化してください。") from e

    ai = aovs.AOVInterface()
    nodes = []
    for aov in aov_names:
        plug = ai.getAOVNode(aov)  # 例: 'aiAOV_diffuse_direct.message'
        if not plug:
            try:
                ai.addAOV(aov)
                plug = ai.getAOVNode(aov)
                print("[NEW] AOV追加:", aov)
            except Exception as ex:
                cmds.warning("[AOV] 追加失敗: {} ({})".format(aov, ex))
                continue
        node = str(plug).split(".", 1)[0]
        if cmds.objExists(node):
            nodes.append(node)
        else:
            cmds.warning("[AOV] ノード未検出: {} (plug={})".format(aov, plug))
    return nodes

def enable_aovs_on_layer(col, aov_nodes, state=True):
    """各 AOV ノードの enabled をレイヤー絶対オーバーライドで制御。"""
    for node in aov_nodes:
        if cmds.attributeQuery("enabled", node=node, exists=True):
            safe_abs_override(col, node, "enabled", bool(state))
        else:
            print("[WARN] {}.enabled が無いのでスキップ".format(node))

# ===== メイン =====
def main(layer_name=LAYER_NAME, aov_list=AOV_LIST):
    ensure_arnold()
    rs = get_rs()

    # レイヤー & コレクション
    layer = get_or_create_layer(rs, layer_name)
    col = create_collection(layer, layer_name)

    # 収集（選択を静的登録。パターン収集にしたい場合は setPattern を使う）
    collect_current_selection(col)

    # AOV 準備
    aov_nodes = ensure_aovs(aov_list)
    print("[INFO] 対象 AOV ノード:", aov_nodes)

    # レイヤーで AOV 有効化（override）
    enable_aovs_on_layer(col, aov_nodes, True)

    # ついでに共通設定のサンプル（必要に応じて調整）
    safe_abs_override(col, "defaultRenderGlobals", "animation", True)
    safe_abs_override(col, "defaultArnoldDriver", "ai_translator", "exr")
    safe_abs_override(col, "defaultRenderGlobals", "imageFilePrefix",
                      "<Scene>/<RenderLayer>/<Camera>")

    rs.switchToLayer(layer)
    print("[DONE] レイヤー '{}'：AOV 一括作成 & 有効化(override) 完了".format(layer_name))

# 実行
if __name__ == "__main__":
    main()
