locals {
  bootstrap_user_data = templatefile("${path.module}/bootstrap/user-data.sh.tftpl", {
    install_runtime_b64 = base64encode(file("${path.module}/bootstrap/install-runtime.sh"))
    nginx_conf_b64      = base64encode(file("${path.module}/bootstrap/nginx.conf"))
    console_unit_b64    = base64encode(file("${path.module}/bootstrap/tictactest-console.service"))
    web_unit_b64        = base64encode(file("${path.module}/bootstrap/tictactest-web.service"))
  })
}
