import jinja2


class TemplateLoader:
    def build_template_loader(self) -> jinja2.Environment:
        template_loader = jinja2.FileSystemLoader("apps/opspilot/")
        template_env = jinja2.Environment(loader=template_loader)
        return template_env


core_template = TemplateLoader().build_template_loader()
