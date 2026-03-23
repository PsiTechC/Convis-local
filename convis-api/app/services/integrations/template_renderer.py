"""
Template Renderer Service
Renders templates with dynamic data using Jinja2-like syntax
"""
import re
from typing import Any, Dict
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class TemplateRenderer:
    """Renders templates with variable substitution and filters"""

    # Pattern to match {{variable}} or {{variable|filter}}
    VARIABLE_PATTERN = re.compile(r'\{\{([^}]+)\}\}')

    @staticmethod
    def get_nested_value(data: Dict[str, Any], path: str, default: Any = "") -> Any:
        """
        Get value from nested dictionary using dot notation
        Example: "customer.email" -> data['customer']['email']
        """
        keys = path.strip().split('.')
        value = data

        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
            elif isinstance(value, list) and key.isdigit():
                try:
                    value = value[int(key)]
                except (IndexError, ValueError):
                    return default
            else:
                return default

            if value is None:
                return default

        return value if value is not None else default

    @staticmethod
    def apply_filter(value: Any, filter_name: str) -> Any:
        """Apply a filter to a value"""
        # DON'T strip the entire filter_name here - it removes important spaces from parameters!
        # We'll handle stripping on a per-case basis

        # Split filter name and parameter BEFORE lowercasing or stripping
        if ':' in filter_name:
            filter_base, filter_param = filter_name.split(':', 1)
            filter_base = filter_base.strip().lower()
            # DON'T strip parameter here - some filters (like join) need to preserve spaces
            # We'll strip on a per-filter basis where needed
        else:
            filter_base = filter_name.strip().lower()
            filter_param = None

        if filter_base == "upper":
            return str(value).upper()

        elif filter_base == "lower":
            return str(value).lower()

        elif filter_base == "title":
            return str(value).title()

        elif filter_base == "capitalize":
            return str(value).capitalize()

        elif filter_base == "strip":
            return str(value).strip()

        elif filter_base == "length":
            return len(value) if hasattr(value, '__len__') else 0

        elif filter_base == "default":
            if filter_param:
                # {{var|default:N/A}} - use parameter as default, preserve case
                return value if value else filter_param
            else:
                # {{var|default}} - use empty string
                return value if value else ""

        elif filter_base == "json":
            import json
            return json.dumps(value)

        elif filter_base == "date":
            if filter_param:
                # Custom date format: {{date|date:%Y/%m/%d}}
                # Strip whitespace from date format (it doesn't need spaces)
                if isinstance(value, datetime):
                    return value.strftime(filter_param.strip())
                return str(value)
            else:
                # Format datetime as date
                if isinstance(value, datetime):
                    return value.strftime("%Y-%m-%d")
                return str(value)

        elif filter_base == "datetime":
            # Format datetime as full datetime
            if isinstance(value, datetime):
                return value.strftime("%Y-%m-%d %H:%M:%S")
            return str(value)

        elif filter_base == "time":
            # Format datetime as time
            if isinstance(value, datetime):
                return value.strftime("%H:%M:%S")
            return str(value)

        elif filter_base == "truncate":
            if filter_param:
                # Custom truncate: {{text|truncate:100}}
                try:
                    max_len = int(filter_param.strip())
                    text = str(value)
                    return text[:max_len] + "..." if len(text) > max_len else text
                except ValueError:
                    return str(value)
            else:
                # Truncate to 50 chars by default
                return str(value)[:50] + "..." if len(str(value)) > 50 else str(value)

        elif filter_base == "first":
            return value[0] if value and len(value) > 0 else ""

        elif filter_base == "last":
            return value[-1] if value and len(value) > 0 else ""

        elif filter_base == "join":
            if filter_param:
                # Custom join: {{list|join: - }} - DON'T strip, preserve spaces in separator!
                return filter_param.join(str(v) for v in value) if isinstance(value, list) else str(value)
            else:
                # Join list with comma
                return ", ".join(str(v) for v in value) if isinstance(value, list) else str(value)

        elif filter_base == "int":
            try:
                return int(value)
            except (ValueError, TypeError):
                return 0

        elif filter_base == "float":
            try:
                return float(value)
            except (ValueError, TypeError):
                return 0.0

        elif filter_base == "round":
            if filter_param:
                # Custom round: {{number|round:2}}
                try:
                    decimals = int(filter_param.strip())
                    return round(float(value), decimals)
                except (ValueError, TypeError):
                    return 0
            else:
                try:
                    return round(float(value))
                except (ValueError, TypeError):
                    return 0

        else:
            logger.warning(f"Unknown filter: {filter_base}")
            return value

    @classmethod
    def render_variable(cls, variable_expr: str, data: Dict[str, Any]) -> str:
        """Render a single variable expression"""
        # Check if there's a filter: {{variable|filter}}
        if '|' in variable_expr:
            parts = variable_expr.split('|', 1)
            var_path = parts[0].strip()
            # DON'T strip the filter part before splitting - some filters need spaces preserved
            # Each filter will be stripped individually in apply_filter
            filters = parts[1].split('|')

            # Get initial value
            value = cls.get_nested_value(data, var_path, default="")

            # Apply filters sequentially
            for filter_name in filters:
                value = cls.apply_filter(value, filter_name)

            return cls._format_value(value)
        else:
            # No filter, just get the value
            var_path = variable_expr.strip()
            value = cls.get_nested_value(data, var_path, default="")
            return cls._format_value(value)

    @staticmethod
    def _format_value(value: Any) -> str:
        """Format a value for output, handling integers vs floats properly"""
        # If it's a float that's actually an integer, format as int
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        # Otherwise convert to string normally
        return str(value)

    @classmethod
    def render(cls, template: str, data: Dict[str, Any]) -> str:
        """
        Render a template with data
        Supports: {{variable}}, {{nested.variable}}, {{variable|filter}}
        """
        if not template:
            return ""

        try:
            def replace_variable(match):
                variable_expr = match.group(1)
                return cls.render_variable(variable_expr, data)

            # Replace all {{...}} expressions
            rendered = cls.VARIABLE_PATTERN.sub(replace_variable, template)
            return rendered

        except Exception as e:
            logger.error(f"Error rendering template: {e}")
            return template

    @classmethod
    def render_dict(cls, template_dict: Dict[str, Any], data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Recursively render all string values in a dictionary
        """
        result = {}

        for key, value in template_dict.items():
            if isinstance(value, str):
                result[key] = cls.render(value, data)
            elif isinstance(value, dict):
                result[key] = cls.render_dict(value, data)
            elif isinstance(value, list):
                result[key] = [
                    cls.render(item, data) if isinstance(item, str) else
                    cls.render_dict(item, data) if isinstance(item, dict) else
                    item
                    for item in value
                ]
            else:
                result[key] = value

        return result

    @classmethod
    def render_string_with_context(
        cls,
        template: str,
        data: Dict[str, Any],
        additional_context: Dict[str, Any] = None
    ) -> str:
        """
        Render template with merged context
        """
        context = {**data}
        if additional_context:
            context.update(additional_context)

        return cls.render(template, context)


# Example usage and filters reference
"""
AVAILABLE FILTERS:
- upper: Convert to uppercase
- lower: Convert to lowercase
- title: Title case
- capitalize: Capitalize first letter
- strip: Remove whitespace
- length: Get length
- default: Use default if empty
- default:value: Use specific default value
- json: Convert to JSON string
- date: Format as YYYY-MM-DD
- datetime: Format as YYYY-MM-DD HH:MM:SS
- time: Format as HH:MM:SS
- date:format: Custom date format
- truncate: Truncate to 50 chars
- truncate:n: Truncate to n chars
- first: Get first element
- last: Get last element
- join: Join list with comma
- join:sep: Join list with separator
- int: Convert to integer
- float: Convert to float
- round: Round to integer
- round:n: Round to n decimals

EXAMPLES:
{{customer.name|upper}}
{{call.duration|round:2}}
{{transcription|truncate:100}}
{{call.created_at|date:%Y-%m-%d}}
{{tags|join: - }}
{{summary|default:No summary available}}
"""
