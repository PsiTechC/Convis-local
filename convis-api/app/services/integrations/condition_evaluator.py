"""
Condition Evaluator Service
Evaluates workflow filter conditions against data
"""
import re
from typing import Any, Dict, List
from app.models.workflow import WorkflowCondition, ConditionOperator
import logging

logger = logging.getLogger(__name__)


class ConditionEvaluator:
    """Evaluates workflow conditions against trigger data"""

    @staticmethod
    def get_nested_value(data: Dict[str, Any], field_path: str) -> Any:
        """
        Get value from nested dictionary using dot notation
        Example: "customer.email" -> data['customer']['email']
        """
        keys = field_path.split('.')
        value = data

        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
            elif isinstance(value, list) and key.isdigit():
                try:
                    value = value[int(key)]
                except (IndexError, ValueError):
                    return None
            else:
                return None

            if value is None:
                return None

        return value

    @staticmethod
    def evaluate_operator(value: Any, operator: ConditionOperator, expected: Any) -> bool:
        """Evaluate a single condition operator"""
        try:
            if operator == ConditionOperator.EQUALS:
                return value == expected

            elif operator == ConditionOperator.NOT_EQUALS:
                return value != expected

            elif operator == ConditionOperator.GREATER_THAN:
                return float(value) > float(expected)

            elif operator == ConditionOperator.GREATER_THAN_OR_EQUAL:
                return float(value) >= float(expected)

            elif operator == ConditionOperator.LESS_THAN:
                return float(value) < float(expected)

            elif operator == ConditionOperator.LESS_THAN_OR_EQUAL:
                return float(value) <= float(expected)

            elif operator == ConditionOperator.CONTAINS:
                if isinstance(value, str):
                    return str(expected) in value
                elif isinstance(value, list):
                    return expected in value
                return False

            elif operator == ConditionOperator.NOT_CONTAINS:
                if isinstance(value, str):
                    return str(expected) not in value
                elif isinstance(value, list):
                    return expected not in value
                return True

            elif operator == ConditionOperator.STARTS_WITH:
                return str(value).startswith(str(expected))

            elif operator == ConditionOperator.ENDS_WITH:
                return str(value).endswith(str(expected))

            elif operator == ConditionOperator.IN:
                if not isinstance(expected, list):
                    expected = [expected]
                return value in expected

            elif operator == ConditionOperator.NOT_IN:
                if not isinstance(expected, list):
                    expected = [expected]
                return value not in expected

            elif operator == ConditionOperator.EXISTS:
                return value is not None

            elif operator == ConditionOperator.NOT_EXISTS:
                return value is None

            elif operator == ConditionOperator.MATCHES_REGEX:
                if value is None:
                    return False
                pattern = re.compile(str(expected))
                return bool(pattern.match(str(value)))

            else:
                logger.warning(f"Unknown operator: {operator}")
                return False

        except (ValueError, TypeError, AttributeError) as e:
            logger.error(f"Error evaluating operator {operator}: {e}")
            return False

    @classmethod
    def evaluate_condition(cls, condition: WorkflowCondition, data: Dict[str, Any]) -> bool:
        """Evaluate a single condition"""
        try:
            # Get the actual value from data using dot notation
            actual_value = cls.get_nested_value(data, condition.field)

            # Evaluate the operator
            result = cls.evaluate_operator(actual_value, condition.operator, condition.value)

            logger.debug(
                f"Condition: {condition.field} {condition.operator} {condition.value} | "
                f"Actual: {actual_value} | Result: {result}"
            )

            return result

        except Exception as e:
            logger.error(f"Error evaluating condition {condition.field}: {e}")
            return False

    @classmethod
    def evaluate_conditions(cls, conditions: List[WorkflowCondition], data: Dict[str, Any]) -> bool:
        """
        Evaluate multiple conditions with AND/OR logic
        Returns True if all conditions pass
        """
        if not conditions:
            return True  # No conditions means always pass

        # Build expression with AND/OR logic
        results = []
        logic_operators = []

        for condition in conditions:
            result = cls.evaluate_condition(condition, data)
            results.append(result)

            # Store logic operator for next condition (default to AND)
            logic = (condition.logic or "AND").upper()
            logic_operators.append(logic)

        # Evaluate with proper AND/OR precedence
        # For now, simple left-to-right evaluation
        final_result = results[0]

        for i in range(1, len(results)):
            logic = logic_operators[i-1]

            if logic == "OR":
                final_result = final_result or results[i]
            else:  # AND
                final_result = final_result and results[i]

        logger.info(f"Conditions evaluation result: {final_result}")
        return final_result

    @classmethod
    def evaluate_conditions_advanced(
        cls,
        conditions: List[WorkflowCondition],
        data: Dict[str, Any],
        default_logic: str = "AND"
    ) -> bool:
        """
        Advanced condition evaluation with grouped logic
        Supports complex expressions like: (A AND B) OR (C AND D)
        """
        if not conditions:
            return True

        # For simple implementation, group by OR
        or_groups = []
        current_and_group = []

        for condition in conditions:
            current_and_group.append(condition)

            # If next logic is OR or this is last condition, finalize group
            logic = (condition.logic or default_logic).upper()
            if logic == "OR" or condition == conditions[-1]:
                # Evaluate this AND group
                and_result = all(
                    cls.evaluate_condition(c, data) for c in current_and_group
                )
                or_groups.append(and_result)
                current_and_group = []

        # OR all groups together
        final_result = any(or_groups)
        logger.info(f"Advanced conditions evaluation: {final_result}")
        return final_result
