from app.modules.employees.employees_dto import EmployeeOut
from app.modules.identity.identity_model import User


def to_employee_out(employee: User) -> EmployeeOut:
    return EmployeeOut.model_validate(employee)
