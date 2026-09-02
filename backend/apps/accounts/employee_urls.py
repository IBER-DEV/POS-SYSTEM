"""Administración del equipo, montada en /api/v1/ y no bajo /auth/.

Entrar y administrar personal son trabajos distintos: /auth/ es por naturaleza
no autenticado, /employees/ e /invitations/ exigen `users.manage`.
"""
from rest_framework.routers import DefaultRouter

from .views import EmployeeViewSet, InvitationViewSet

router = DefaultRouter()
router.register("employees", EmployeeViewSet, basename="employee")
router.register("invitations", InvitationViewSet, basename="invitation")

urlpatterns = router.urls
