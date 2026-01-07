import frappe
import secrets
import frappe.utils

def after_install():
    if not frappe.conf.get("jwt_secret"):
        secret = secrets.token_hex(64)  # 128-char hex

        frappe.conf["jwt_secret"] = secret
        frappe.local.conf.jwt_secret = secret

        frappe.utils.write_json(
            frappe.local.site_path + "/site_config.json",
            frappe.conf,
            pretty=True
        )