def get_mesh_info(mesh_layer):
    """
    Extract and infer as much information as possible from a mesh layer.
    Returns a dictionary with keys: min, max, spread, mean, pixel_size, units, origin, axis_order, source, warnings.
    """
    info = {}
    # 1. Bounding box
    verts = None
    if hasattr(mesh_layer, 'data') and isinstance(mesh_layer.data, tuple) and len(mesh_layer.data) > 0:
        verts = mesh_layer.data[0]
    if verts is not None:
        info['min'] = verts.min(axis=0)
        info['max'] = verts.max(axis=0)
        info['spread'] = info['max'] - info['min']
        info['mean'] = verts.mean(axis=0)
    # 2. Units and pixel size
    meta = getattr(mesh_layer, 'metadata', {})
    info['pixel_size'] = meta.get('pixel_size', None)
    info['units'] = meta.get('units', None)
    # 3. Origin
    info['origin'] = meta.get('origin', None)
    # 4. Axis order (if available)
    info['axis_order'] = meta.get('axis_order', None)
    # 5. Provenance
    info['source'] = meta.get('source_path', None)
    # 6. Heuristics (example: guess units based on spread)
    if verts is not None and info['pixel_size'] is None:
        spread = verts.max(axis=0) - verts.min(axis=0)
        if spread.max() > 1000:
            info['guessed_units'] = 'pixels (large spread)'
        elif spread.max() < 10:
            info['guessed_units'] = 'nm (small spread)'
        else:
            info['guessed_units'] = 'unknown'
    # 7. Warnings
    info['warnings'] = []
    if info['pixel_size'] is None:
        info['warnings'].append('No pixel size in metadata.')
    if info['units'] is None:
        info['warnings'].append('No units in metadata.')
    if verts is None:
        info['warnings'].append('No vertices found in mesh_layer.data.')
    return info 