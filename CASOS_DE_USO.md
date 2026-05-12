Casos de uso (version para presentacion)

UC-01 Inicio de sesion (usuario/operativo)
- Actor: Usuario u Operativo
- Precondicion: Cuenta activa con contrasena
- Flujo: Ingresa usuario y contrasena -> Acceso al dashboard
- Resultado: Sesion iniciada

UC-02 Inicio de sesion con certificado (admin/coordinador)
- Actor: Admin o Coordinador
- Precondicion: Cuenta activa con certificado asignado
- Flujo: Ingresa usuario, contrasena y adjunta certificado -> Acceso
- Resultado: Sesion iniciada con validacion de certificado

UC-03 Creacion de usuario critico con certificado
- Actor: Admin
- Precondicion: Admin autenticado
- Flujo: Captura usuario/rol/datos -> Firma con certificado del admin ->
  Sistema genera certificado (si no se adjunta) y lo guarda en certs/
- Resultado: Usuario creado con certificado asociado

UC-04 Registro de expediente
- Actor: Usuario
- Precondicion: Usuario autenticado
- Flujo: Captura datos -> Sistema cifra y guarda -> Queda en borrador
- Resultado: Expediente creado

UC-05 Canalizacion por niveles
- Actor: Usuario/Operativo/Coordinador/Admin
- Precondicion: Expediente en estado correspondiente
- Flujo: Cada rol avanza a su siguiente estado
- Resultado: Expediente pasa por flujo completo hasta cerrado

UC-06 Validacion coordinador con firma
- Actor: Coordinador
- Precondicion: Expediente en revision de coordinacion
- Flujo: Adjunta certificado -> Firma avance -> Expediente pasa a admin
- Resultado: Expediente validado

UC-07 Solicitud de eliminacion con firma
- Actor: Coordinador
- Precondicion: Expediente en revision de coordinacion
- Flujo: Ingresa motivo + adjunta certificado -> Envia solicitud
- Resultado: Solicitud pendiente para admin

UC-08 Resolucion de solicitud con firma
- Actor: Admin
- Precondicion: Solicitud pendiente
- Flujo: Adjunta certificado -> Aprueba o rechaza
- Resultado: Solicitud resuelta y bitacora actualizada

UC-09 Cierre de expediente con firma
- Actor: Admin
- Precondicion: Expediente validado por coordinacion
- Flujo: Adjunta certificado -> Cierra expediente
- Resultado: Expediente cerrado

UC-10 Limpieza de bitacora con firma
- Actor: Admin
- Precondicion: Admin autenticado
- Flujo: Adjunta certificado -> Confirma limpieza
- Resultado: Bitacora limpiada

UC-11 Eliminacion de usuario con firma
- Actor: Admin
- Precondicion: Usuario no es admin de contingencia y no es el admin en sesion
- Flujo: Adjunta certificado -> Confirma eliminacion
- Resultado: Usuario eliminado

UC-12 Contingencia admin
- Actor: Admin de contingencia
- Precondicion: Cuenta admin de contingencia activa
- Flujo: Inicia sesion y opera en caso de contingencia
- Resultado: Continuidad operativa
