config_test = executable(
  'test-config',
  'test-config.c',
  wl_proto_headers,
  link_with: [common, misc, tokenize],
  dependencies: [pixman, xkb, fontconfig, wayland_client, fcft, tllist])

test('config', config_test)
