-- CreateTable
CREATE TABLE "assets" (
    "id" SERIAL NOT NULL,
    "job_id" TEXT NOT NULL,
    "file_path" TEXT NOT NULL,
    "prompt" TEXT NOT NULL,
    "model" TEXT NOT NULL,
    "asset_type" TEXT NOT NULL,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "file_size" INTEGER,
    "duration" DOUBLE PRECISION,

    CONSTRAINT "assets_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "assets_job_id_key" ON "assets"("job_id");
