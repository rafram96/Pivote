"""
Orquestador del pipeline backend — máquina de estados con checkpoints.

Uso mínimo:
    from orquestador import Motor, etapas_esqueleto
    from orquestador.repositorio import RepositorioArchivos

    motor = Motor(etapas_esqueleto(), RepositorioArchivos(Path("./jobs")))
    job = motor.crear_job(espejo_dict)
    job = motor.correr(job.job_id)              # reanudable
    job = motor.resolver_revision(job.job_id, n_prof=3, n_exp=2, dato={"cui": "2338373"})
"""
from .etapas import Contexto, ErrorEstructural, EtapaBase, EtapaIngesta, EtapaStub, etapas_esqueleto
from .motor import Motor
from .repositorio import Repositorio, RepositorioArchivos, RepositorioMemoria

__all__ = [
    "Contexto", "ErrorEstructural", "EtapaBase", "EtapaIngesta", "EtapaStub",
    "etapas_esqueleto", "Motor", "Repositorio", "RepositorioArchivos",
    "RepositorioMemoria",
]
