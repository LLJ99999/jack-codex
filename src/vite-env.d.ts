/// <reference types="vite/client" />

// 让 TypeScript 认识 Vite 的资源导入（png / svg / woff2 等）
declare module "*.png" {
  const src: string;
  export default src;
}
declare module "*.jpg" {
  const src: string;
  export default src;
}
declare module "*.svg" {
  const src: string;
  export default src;
}
