def register_generators(registry):
    registry.register("sample-api", lambda root, target, changed: "Generated sample API.")
