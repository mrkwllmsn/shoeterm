config_test = executable(
  'test-config',
  'test-config.c',
  srgb_funcs,
  wl_proto_headers,
  link_with: [common, tokenize],
  dependencies: [pixman, xkb, fontconfig, wayland_client, fcft, tllist])

test('config', config_test)
