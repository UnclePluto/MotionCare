export {
  motionTrainingUploadErrorMessage as shoulderPressUploadErrorMessage,
  runMotionTrainingUploadWorkflow as runShoulderPressUploadWorkflow,
  runPendingSegmentUploads,
  type MotionTrainingUploadEvent as ShoulderPressUploadEvent,
  type MotionTrainingUploadPhase as ShoulderPressUploadPhase,
  type PendingSegmentUploadDependencies
} from '../../features/motion-training/workflow'
