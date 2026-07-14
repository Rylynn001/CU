import json
import pathlib

try:
    from pxr import Gf, Sdf, Usd, UsdGeom, UsdLux, UsdUtils
    OPENUSD_AVAILABLE = True
except ImportError:
    OPENUSD_AVAILABLE = False


def require_openusd() -> None:
    if not OPENUSD_AVAILABLE:
        raise RuntimeError('OpenUSD runtime is not installed; install usd-core for Python 3.11')


def open_stage(root_path: str, session_path: str | None = None):
    require_openusd()
    root = Sdf.Layer.FindOrOpen(root_path)
    if not root: raise ValueError('Unable to open USD root layer')
    if session_path:
        session = Sdf.Layer.FindOrOpen(session_path) or Sdf.Layer.CreateNew(session_path)
        return Usd.Stage.Open(root, session)
    return Usd.Stage.Open(root)


def _prim_info(prim) -> dict:
    variants = {}
    sets = prim.GetVariantSets()
    for name in sets.GetNames():
        variant_set = sets.GetVariantSet(name)
        variants[name] = {'selection': variant_set.GetVariantSelection(), 'options': variant_set.GetVariantNames()}
    info = {
        'path': str(prim.GetPath()), 'name': prim.GetName(), 'type': prim.GetTypeName() or 'Scope',
        'active': prim.IsActive(), 'loaded': prim.IsLoaded(), 'has_payload': prim.HasPayload(),
        'variants': variants, 'children': [],
    }
    if prim.IsA(UsdGeom.Imageable):
        info['visible'] = UsdGeom.Imageable(prim).ComputeVisibility() != UsdGeom.Tokens.invisible
    if prim.IsA(UsdGeom.Xformable):
        matrix = UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
        info['transform'] = [float(value) for row in matrix for value in row]
    return info


def describe_stage(root_path: str, session_path: str | None = None) -> dict:
    stage = open_stage(root_path, session_path)
    nodes, by_path = [], {}
    for prim in stage.TraverseAll():
        item = _prim_info(prim); by_path[item['path']] = item
        parent = str(prim.GetParent().GetPath())
        (by_path[parent]['children'] if parent in by_path else nodes).append(item)
    cameras = [str(prim.GetPath()) for prim in stage.Traverse() if prim.IsA(UsdGeom.Camera)]
    lights = [str(prim.GetPath()) for prim in stage.Traverse() if prim.IsA(UsdLux.LightAPI)]
    return {
        'prims': nodes, 'cameras': cameras, 'lights': lights,
        'up_axis': UsdGeom.GetStageUpAxis(stage), 'meters_per_unit': UsdGeom.GetStageMetersPerUnit(stage),
        'start_time': stage.GetStartTimeCode(), 'end_time': stage.GetEndTimeCode(),
        'layers': [layer.identifier for layer in stage.GetLayerStack()],
        'composition_errors': [str(error) for error in stage.GetCompositionErrors()],
    }


def apply_session(root_path: str, session_path: str, state: dict) -> None:
    stage = open_stage(root_path, session_path)
    stage.SetEditTarget(stage.GetSessionLayer())
    for path, visible in state.get('visibility', {}).items():
        prim = stage.GetPrimAtPath(path)
        if prim and prim.IsA(UsdGeom.Imageable):
            (UsdGeom.Imageable(prim).MakeVisible if visible else UsdGeom.Imageable(prim).MakeInvisible)()
    for path, selections in state.get('variants', {}).items():
        prim = stage.GetPrimAtPath(path)
        if prim:
            for name, selection in selections.items(): prim.GetVariantSets().GetVariantSet(name).SetVariantSelection(selection)
    for path, loaded in state.get('payloads', {}).items():
        prim = stage.GetPrimAtPath(path)
        if prim: (prim.Load if loaded else prim.Unload)()
    for path, values in state.get('transforms', {}).items():
        prim = stage.GetPrimAtPath(path)
        if prim and len(values) == 16:
            xform = UsdGeom.Xformable(prim); xform.ClearXformOpOrder(); xform.AddTransformOp().Set(Gf.Matrix4d(*values))
    stage.GetSessionLayer().Save()


def export_preview(root_path: str, output_path: str, session_path: str | None = None) -> None:
    open_stage(root_path, session_path).Flatten().Export(output_path)


def package_usdz(root_path: str, output_path: str, session_path: str | None = None) -> None:
    require_openusd()
    source = root_path
    if session_path and pathlib.Path(session_path).exists():
        flattened = pathlib.Path(output_path).with_suffix('.flattened.usdc')
        open_stage(root_path, session_path).Flatten().Export(str(flattened))
        source = str(flattened)
    if not UsdUtils.CreateNewUsdzPackage(Sdf.AssetPath(source), output_path):
        raise RuntimeError('Failed to create USDZ package')
    if source != root_path: pathlib.Path(source).unlink(missing_ok=True)
