declare module "*.css";
declare module "*?worker&inline" { const WorkerConstructor: { new (): Worker }; export default WorkerConstructor; }
