# Kavak AI Agent

Asistente de IA para ayudar a los clientes a encontrar su auto ideal en el catálogo de Kavak.

## Prueba de la Aplicación

### 1. Configurar WhatsApp Sandbox
1. Abrir WhatsApp en tu teléfono
2. Agregar el número: +14155238886
3. Enviar mensaje: `join look-quietly`
4. Esperar confirmación de que te has unido al sandbox

Alternativamente, puedes:
- Hacer clic en [este enlace](http://wa.me/+14155238886?text=join%20look-quietly) para abrir WhatsApp directamente
- Escanear el código QR (si está disponible)
- Enviar mensaje: `join look-quietly`

### 2. Probar la Aplicación
Una vez unido al sandbox, puedes probar los siguientes comandos:

#### Búsqueda de Autos
```
Hola, busco un auto económico familiar
```
```
Muéstrame Volkswagens Golf
```
```
Autos entre 300 y 400 mil pesos
```
```
Autos con bluetooth y carplay
```

#### Financiamiento
```
Calcula el financiamiento para un auto de 500 mil pesos con enganche de 100 mil
```
```
Muéstrame opciones a 48 meses
```

#### Detalles
```
Dame más detalles del Volkswagen Golf GTI Performance
```
```
Muéstrame más Chevrolets Spark ACTIV D
```

### 3. Verificar Funcionamiento
1. **Respuestas del Bot**:
   - Deberías recibir respuestas en segundos
   - Las respuestas deben ser relevantes a tu búsqueda
   - El bot debe mantener el contexto de la conversación

2. **Monitoreo**:
   - Revisar CloudWatch Logs para ver el flujo de la conversación
   - Verificar Step Functions para ver el procesamiento
   - Monitorear DynamoDB para ver las consultas

3. **Solución de Problemas**:
   - Si no recibes respuesta, verificar:
     - Que estás en el sandbox correcto
     - Que el webhook está configurado
     - Que las funciones Lambda están activas
   - Si la respuesta es incorrecta:
     - Verificar logs de la función de chat
     - Revisar embeddings en DynamoDB
     - Comprobar el catálogo de autos

### 4. Ejemplos de Conversación
```
Usuario: Hola
Bot: ¡Hola! Soy tu asistente para encontrar el auto ideal en Kavak. ¿Qué tipo de auto estás buscando?

Usuario: Busco un auto económico familiar
Bot: Entiendo que buscas un auto económico y familiar. Te sugiero estas opciones:
1. Chevrolet Spark ACTIV D 2021 - $325,000
   - 5 puertas
   - Bluetooth y CarPlay
   - Económico en consumo
[...]

Usuario: ¿Tiene bluetooth?
Bot: Sí, el Chevrolet Spark ACTIV D incluye Bluetooth y CarPlay. ¿Te gustaría saber más detalles o ver otras opciones?

Usuario: Muéstrame otras opciones
Bot: Aquí tienes más opciones económicas y familiares:
1. Volkswagen Vento 2020 - $350,000
   - 4 puertas
   - Bluetooth y CarPlay
   - Espacioso
[...]
```

### 5. Notas Importantes
- El sandbox de WhatsApp tiene límites de uso
- Las respuestas pueden tardar unos segundos
- El bot mantiene contexto por 24 horas
- Los embeddings se actualizan diariamente
- Las búsquedas son semánticas, puedes usar lenguaje natural

## Características

### Búsqueda Semántica de Autos
- Búsqueda por descripción natural (ej: "un auto económico familiar")
- Búsqueda por marca y modelo específicos
- Búsqueda por rango de precio y año
- Búsqueda por características específicas (bluetooth, carplay)
- Resultados ordenados por relevancia

### Características Disponibles
- Marca, modelo, versión y año
- Precio y kilometraje
- Dimensiones (largo, ancho, altura)
- Características (bluetooth, carplay)

### Financiamiento
- Cálculo de opciones de financiamiento
- Diferentes plazos (36 a 72 meses)
- Tasa de interés personalizable
- Cálculo de mensualidades

### Conversación Natural
- Mantiene contexto de la conversación
- Resumen automático de preferencias
- Respuestas personalizadas
- Manejo de múltiples criterios de búsqueda

## Arquitectura

### Diagrama General
```mermaid
graph TB
    subgraph Cliente
        WA[WhatsApp] -->|Mensaje| TW[Twilio]
    end

    subgraph AWS
        subgraph API Gateway
            TW -->|Webhook| APIG[API Gateway]
        end

        subgraph Step Functions
            APIG -->|Inicia| SF1[Flujo de Conversación]
            SF1 -->|Procesa| L1[Lambda Chat]
            SF1 -->|Actualiza| L2[Lambda Embeddings]
            SF1 -->|Responde| L3[Lambda Webhook]
            
            CW[CloudWatch Events] -->|Diario| SF2[Flujo de Embeddings]
            SF2 -->|Actualiza| L2
        end

        subgraph DynamoDB
            L1 -->|Lee/Escribe| DB1[Conversaciones]
            L2 -->|Lee/Escribe| DB2[Embeddings]
            L2 -->|Lee| DB3[Catálogo]
        end

        subgraph OpenAI
            L1 -->|Consulta| GPT[GPT-3.5 Turbo]
            L2 -->|Genera| EMB[Embeddings API]
        end
    end

    L3 -->|Respuesta| WA
```

### Flujos Detallados

#### 1. Flujo de Conversación
```mermaid
stateDiagram-v2
    [*] --> RecibirMensaje
    RecibirMensaje --> ProcesarMensaje
    ProcesarMensaje --> VerificarContexto
    
    VerificarContexto --> BuscarEmbedding: Necesita Embedding
    VerificarContexto --> GenerarRespuesta: No necesita Embedding
    
    BuscarEmbedding --> ActualizarEmbedding: No existe
    BuscarEmbedding --> GenerarRespuesta: Existe
    
    ActualizarEmbedding --> GenerarRespuesta
    GenerarRespuesta --> EnviarRespuesta
    EnviarRespuesta --> ActualizarContexto
    ActualizarContexto --> [*]
    
    state VerificarContexto {
        [*] --> ConsultarDynamoDB
        ConsultarDynamoDB --> VerificarTimestamp
        VerificarTimestamp --> [*]
    }
    
    state GenerarRespuesta {
        [*] --> ConsultarGPT
        ConsultarGPT --> FormatearRespuesta
        FormatearRespuesta --> [*]
    }
```

#### 2. Flujo de Actualización de Embeddings
```mermaid
stateDiagram-v2
    [*] --> TriggerDiario
    TriggerDiario --> ObtenerCatalogo
    
    state ProcesarLote {
        [*] --> ObtenerLote
        ObtenerLote --> GenerarEmbedding
        GenerarEmbedding --> GuardarDynamoDB
        GuardarDynamoDB --> [*]
    }
    
    ObtenerCatalogo --> ProcesarLote
    ProcesarLote --> VerificarMasLotes
    
    VerificarMasLotes --> ProcesarLote: Hay más lotes
    VerificarMasLotes --> Finalizar: No hay más lotes
    Finalizar --> [*]
    
    state GenerarEmbedding {
        [*] --> NormalizarTexto
        NormalizarTexto --> ConsultarOpenAI
        ConsultarOpenAI --> [*]
    }
```

### Componentes y Responsabilidades

#### 1. Frontend (WhatsApp + Twilio)
- **WhatsApp**: Interfaz de usuario
- **Twilio**: 
  - Recibe mensajes de WhatsApp
  - Envía mensajes al webhook
  - Maneja la sesión de WhatsApp

#### 2. API Gateway
- Expone endpoints para:
  - Webhook de Twilio
  - Actualización de embeddings
  - Monitoreo y salud

#### 3. Step Functions
- **Flujo de Conversación**:
  - Orquesta el procesamiento de mensajes
  - Maneja actualizaciones de embeddings
  - Gestiona el contexto de la conversación
  - Coordina la generación de respuestas

- **Flujo de Embeddings**:
  - Se ejecuta diariamente
  - Procesa el catálogo en lotes
  - Actualiza embeddings desactualizados
  - Maneja errores y reintentos

#### 4. Lambda Functions
- **Chat**:
  - Procesa mensajes del usuario
  - Consulta GPT-3.5
  - Maneja el contexto de la conversación
  - Genera respuestas personalizadas

- **Embeddings**:
  - Genera embeddings para autos
  - Actualiza embeddings existentes
  - Maneja la normalización de texto
  - Gestiona la caché de embeddings

- **Webhook**:
  - Recibe webhooks de Twilio
  - Valida mensajes entrantes
  - Envía respuestas a WhatsApp
  - Maneja errores de comunicación

#### 5. Bases de Datos
- **Conversaciones**:
  - Almacena historial de chat
  - Mantiene contexto de conversación
  - Guarda resúmenes de preferencias

- **Embeddings**:
  - Almacena embeddings de autos
  - Mantiene metadatos de actualización
  - Optimiza búsquedas semánticas

- **Catálogo**:
  - Almacena información de autos
  - Mantiene características y precios
  - Actualización periódica

#### 6. Servicios Externos
- **OpenAI**:
  - GPT-3.5 Turbo para conversación
  - Embeddings API para búsqueda semántica
  - Optimización de prompts

## Desarrollo

### Requisitos
- Python 3.9+
- AWS SAM CLI
- Docker (para desarrollo local)
- OpenAI API Key
- Cuenta de AWS con permisos adecuados
- Cuenta de Twilio (para WhatsApp)

### Variables de Entorno
```bash
# OpenAI
OPENAI_API_KEY=sk-...

# AWS
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=...
AWS_REGION=us-east-1

# DynamoDB
CATALOG_TABLE=kavak-catalog-{stage}
EMBEDDINGS_TABLE=kavak-embeddings-{stage}
STAGE=dev|prod

# Twilio
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...
TWILIO_PHONE_NUMBER=whatsapp:+14155238886  # Número de WhatsApp de Twilio
```

### Tutorial de Configuración

#### 1. Configurar AWS
1. Crear una cuenta en AWS si no tienes una
2. Crear un usuario IAM con los siguientes permisos:
   - AWSLambdaFullAccess
   - AmazonDynamoDBFullAccess
   - AmazonAPIGatewayAdministrator
   - CloudWatchFullAccess
   - AWSXRayFullAccess
   - AWSStepFunctionsFullAccess
3. Generar credenciales de acceso (Access Key y Secret Key)
4. Configurar AWS CLI:
```bash
aws configure
# Ingresar Access Key, Secret Key y región (ej: us-east-1)
```

#### 2. Configurar Twilio
1. Crear una cuenta en Twilio (https://www.twilio.com)
2. Obtener Account SID y Auth Token del dashboard
3. Configurar WhatsApp Sandbox:
   - Ir a Twilio Console > Messaging > Try it out > Send a WhatsApp message
   - Seguir las instrucciones para activar el sandbox
   - Guardar el número de WhatsApp de Twilio (formato: whatsapp:+14155238886)
4. Configurar webhook:
   - En Twilio Console > Messaging > Settings > WhatsApp Sandbox Settings
   - Configurar "WHEN A MESSAGE COMES IN" con la URL de tu API Gateway
   - URL ejemplo: `https://{api-id}.execute-api.{region}.amazonaws.com/{stage}/webhook`

#### 3. Configurar OpenAI
1. Crear una cuenta en OpenAI (https://platform.openai.com)
2. Generar una API Key
3. Verificar que la API Key tenga acceso a:
   - GPT-3.5 Turbo
   - Embeddings API

#### 4. Configurar el Proyecto
1. Clonar el repositorio:
```bash
git clone git@github.com:DanteRangel/kavak-ai-agent.git
cd kavak-ai-agent
```

2. Crear y activar entorno virtual:
```bash
python -m venv venv
source venv/bin/activate  # En Windows: venv\Scripts\activate
```

3. Instalar dependencias:
```bash
pip install -r requirements.txt
```

4. Crear archivo de variables de entorno:
```bash
cp .env.example .env
# Editar .env con tus credenciales
```

5. Iniciar DynamoDB local:
```bash
docker run -p 8000:8000 amazon/dynamodb-local
```

6. Crear tablas localmente:
```bash
aws dynamodb create-table \
    --table-name kavak-catalog-dev \
    --attribute-definitions AttributeName=stockId,AttributeType=S \
    --key-schema AttributeName=stockId,KeyType=HASH \
    --provisioned-throughput ReadCapacityUnits=5,WriteCapacityUnits=5 \
    --endpoint-url http://localhost:8000

aws dynamodb create-table \
    --table-name kavak-embeddings-dev \
    --attribute-definitions AttributeName=stockId,AttributeType=S \
    --key-schema AttributeName=stockId,KeyType=HASH \
    --provisioned-throughput ReadCapacityUnits=5,WriteCapacityUnits=5 \
    --endpoint-url http://localhost:8000
```

7. Importar catálogo de prueba:
```bash
python -m app.scripts.import_catalog sample_caso_ai_engineer.csv --table kavak-catalog-dev
```

8. Probar localmente:
```bash
sam local start-api
```

#### 5. Despliegue a AWS
1. Construir la aplicación:
```bash
sam build
```

2. Desplegar a desarrollo:
```bash
sam deploy --guided --stack-name kavak-ai-agent-dev
```

3. Verificar Step Functions:
   - Ir a AWS Console > Step Functions
   - Verificar que se creó el flujo:
     - `kavak-ai-agent-dev-conversation-flow`
     ```

4. Actualizar webhook de Twilio:
   - Copiar la URL de API Gateway del output de SAM
   - Actualizar en Twilio Console > Messaging > Settings > WhatsApp Sandbox Settings
   - Asegurarse que el webhook apunte al endpoint que inicia el flujo de conversación

5. Probar el webhook:
   - Enviar "Hola" al número de WhatsApp de Twilio
   - Verificar logs en CloudWatch
   - Verificar el flujo en Step Functions
   - Verificar respuesta en WhatsApp

#### 6. Monitoreo
1. CloudWatch Logs:
   - Revisar logs de las funciones Lambda
   - Configurar alarmas para errores

2. X-Ray:
   - Verificar trazas de las funciones
   - Analizar tiempos de respuesta

3. DynamoDB:
   - Monitorear capacidad de lectura/escritura
   - Verificar tamaño de las tablas

4. Step Functions:
   - Monitorear ejecuciones de los flujos
   - Revisar métricas de éxito/error
   - Configurar alarmas para fallos
   - Verificar tiempos de ejecución

### Estructura del Proyecto
```
kavak-ai-agent/
├── template.yaml         # Configuración de SAM
├── requirements.txt      # Dependencias de Python
├── app/
│   ├── scripts/         # Scripts de utilidad
│   │   └── import_catalog.sh    # Script para importar catálogo
│   ├── functions/       # Funciones Lambda
│   │   ├── chat/       # Función de chat
│   │   ├── webhook/    # Webhook de WhatsApp
│   │   └── update_embeddings/  # Actualización de embeddings
│   ├── core/           # Código compartido
│   │   ├── services/   # Servicios compartidos
│   │   └── utils/      # Utilidades
│   └── layers/         # Capas Lambda compartidas
└── tests/              # Pruebas unitarias y de integración
```

### Importar Catálogo

#### 1. Preparar el CSV
El archivo CSV debe tener las siguientes columnas:
- `stockId`: Identificador único del auto
- `make`: Marca del auto
- `model`: Modelo del auto
- `version`: Versión del auto (opcional)
- `year`: Año del auto
- `price`: Precio en pesos
- `km`: Kilometraje
- `bluetooth`: "Sí" o "No"
- `carPlay`: "Sí" o "No"
- `largo`: Largo en mm
- `ancho`: Ancho en mm
- `altura`: Altura en mm

#### 2. Requisitos
```bash
# Instalar dependencias
pip install csvkit  # Para csvjson
pip install jq      # Para procesamiento JSON
```

#### 3. Usar el Script de Importación
```bash
# Dar permisos de ejecución al script
chmod +x app/scripts/import_catalog.sh

# Importar a desarrollo
./app/scripts/import_catalog.sh catalogo.csv kavak-catalog-dev

# Importar a producción
./app/scripts/import_catalog.sh catalogo.csv kavak-catalog-prod
```

El script:
- Convierte el CSV a JSON usando `csvjson`
- Transforma los tipos de datos automáticamente:
  - Números a tipo N
  - Booleanos a tipo BOOL
  - Texto a tipo S
- Filtra campos nulos o vacíos
- Importa registro por registro a DynamoDB
- Muestra progreso de importación

#### 4. Verificar la Importación
```bash
# Contar registros en la tabla
aws dynamodb scan \
    --table-name kavak-catalog-dev \
    --select COUNT \
    --region us-east-1

# Verificar algunos registros
aws dynamodb scan \
    --table-name kavak-catalog-dev \
    --limit 5 \
    --region us-east-1

# Verificar estructura de un registro
aws dynamodb get-item \
    --table-name kavak-catalog-dev \
    --key '{"stockId": {"S": "ID_DEL_AUTO"}}' \
    --region us-east-1
```

#### 5. Solución de Problemas
1. **Error de Dependencias**:
   ```bash
   # Verificar instalación de csvkit
   which csvjson
   
   # Verificar instalación de jq
   which jq
   ```

2. **Error de Credenciales**:
   ```bash
   # Verificar credenciales
   aws sts get-caller-identity
   
   # Configurar credenciales si es necesario
   aws configure
   ```

3. **Error de Formato CSV**:
   - Verificar que el CSV tenga las columnas requeridas
   - Asegurar que los valores numéricos sean números
   - Verificar que los booleanos sean "Sí" o "No"

4. **Error de Permisos**:
   - Verificar que el usuario IAM tenga permisos para DynamoDB
   - Agregar política `AmazonDynamoDBFullAccess` si es necesario

#### 6. Monitoreo
1. **CloudWatch Metrics**:
   - `ConsumedWriteCapacityUnits`
   - `ThrottledRequests`
   - `SystemErrors`

2. **DynamoDB Console**:
   - Verificar métricas de la tabla
   - Revisar capacidad consumida
   - Monitorear errores de throttling

## Uso

### Búsqueda de Autos
- Por descripción: "busca un auto económico familiar"
- Por marca/modelo: "muéstrame Volkswagens Golf"
- Por precio: "autos entre 300 y 400 mil pesos"
- Por características: "autos con bluetooth y carplay"

### Financiamiento
- "calcula el financiamiento para un auto de 500 mil pesos con enganche de 100 mil"
- "muéstrame opciones a 48 meses"

### Detalles
- "dame más detalles del Volkswagen Golf GTI Performance"
- "muéstrame más Chevrolets Spark ACTIV D"

## Arquitectura AWS

El proyecto utiliza una arquitectura serverless con los siguientes componentes:

- **AWS Lambda**: Para el procesamiento de mensajes y recomendaciones
- **Amazon API Gateway**: Para exponer los endpoints de la API
- **Amazon DynamoDB**: Para almacenar el catálogo, embeddings y conversaciones
- **Amazon CloudWatch**: Para monitoreo y logging
- **AWS X-Ray**: Para trazabilidad
- **AWS Step Functions**: Para orquestar el flujo de conversación y actualización de embeddings

### Flujos de Step Functions

#### 1. Flujo de Conversación
```mermaid
graph LR
    A[Webhook] --> B[Procesar Mensaje]
    B --> C{¿Necesita Embedding?}
    C -->|Sí| D[Actualizar Embedding]
    C -->|No| E[Generar Respuesta]
    D --> E
    E --> F[Enviar Respuesta]
    F --> G[Actualizar Contexto]
```

> **Nota**: La actualización de embeddings se maneja internamente dentro del flujo de conversación cuando es necesario, no como un flujo separado.

#### 2. Flujo de Actualización de Embeddings
```mermaid
graph LR
    A[Trigger Diario] --> B[Obtener Catálogo]
    B --> C[Procesar Lote]
    C --> D{¿Más Lotes?}
    D -->|Sí| C
    D -->|No| E[Finalizar]
```

## Roadmap

1. **Fase 1: MVP**
   - Implementación básica de funciones Lambda
   - Integración con WhatsApp
   - Sistema de recomendación semántico
   - Despliegue inicial en AWS

2. **Fase 2: Mejoras**
   - Optimización de costos
   - Implementación de caché
   - Mejoras en recomendaciones
   - Optimización de prompts

3. **Fase 3: Producción**
   - Monitoreo avanzado
   - Auto-scaling
   - Integración con sistemas existentes
   - Implementación de CI/CD

## Métricas de Evaluación

- Precisión en recomendaciones
- Tasa de conversión
- Satisfacción del usuario
- Tiempo de respuesta
- Tasa de resolución de consultas
- Costos operativos
- Tiempo de ejecución Lambda

## Contribución

1. Fork el proyecto
2. Crear una rama para tu feature (`git checkout -b feature/AmazingFeature`)
3. Commit tus cambios (`git commit -m 'Add some AmazingFeature'`)
4. Push a la rama (`git push origin feature/AmazingFeature`)
5. Abrir un Pull Request

## Licencia

Este proyecto es privado y confidencial para Kavak. 