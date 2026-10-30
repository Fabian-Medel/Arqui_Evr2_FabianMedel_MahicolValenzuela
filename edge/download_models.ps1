$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Force -Path "$PSScriptRoot\models" | Out-Null
$Base = 'https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models'
Invoke-WebRequest "$Base/face_detection_yunet/face_detection_yunet_2023mar.onnx" -OutFile "$PSScriptRoot\models\yunet.onnx" -UseBasicParsing
Invoke-WebRequest "$Base/face_recognition_sface/face_recognition_sface_2021dec.onnx" -OutFile "$PSScriptRoot\models\sface.onnx" -UseBasicParsing
Write-Output 'Modelos descargados.'
