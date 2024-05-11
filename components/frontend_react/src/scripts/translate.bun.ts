// Copyright 2024 Google LLC
//
// Licensed under the Apache License, Version 2.0 (the License);
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     https://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

// DO NOT USE. Not working. Waiting for Bun to support Google Cloud and file directory funcitons

// Object.defineProperty(exports, "__esModule", { value: true })
// const fs = require("fs/promises")
// import { fs } from "fs/promises"
// import { createRequire } from "node:module"
import fs from "fs/promises"
import { difference } from "ramda"

// const require = createRequire(import.meta.url)
import { Translate } from "@google-cloud/translate/build/src/v2"
// const { Translate } = require("@google-cloud/translate").v2

// import { targetLanguages } from "@/utils/lang"
// import { resolve } from "path"
const targetLanguages = [
  { code: "en", name: "English", flag: "🇺🇸" },
  { code: "es", name: "Español", flag: "🇲🇽" },
  { code: "de", name: "Deutsch", flag: "🇩🇪" },
]
// require("../public/locales/targetLangs.json") as string[]

const translateClient = new Translate()

const SOURCE_BASE = "public/locales"
const ENGLISH_BASE = `${SOURCE_BASE}/en`
const TRANSLATION_BATCH_SIZE = 100

// const fileExists = async (path: string) => await Bun.file(path).exists()
// const writeFileContents = (file: string, contents: string) => {
//   return
//   const writer = bfile.writer()
//   writer.write(contents)
//   writer.end()
// }

// const ensureLanguageFileExists = async (dir: string, file: string) => {
//   const bfile = Bun.file(dir)
//   const exists = await bfile.exists()
//   console.log({ exists, dir, file })
//   if (!exists) {
//     // await Bun.write(bfile, "{}")
//   }

//   // if (!(await fileExists(dir))) {
//   //   try {
//   //     await fs.mkdir(dir)
//   //   } catch (_) {}
//   // }

//   // if (!(await fileExists(file))) {
//   //   await fs.writeFile(file, JSON.stringify({}))
//   // }
// }

const fileExists = async (path: string) =>
  !!(await fs.stat(path).catch((_) => false))

const ensureLanguageFileExists = async (dir: string, file: string) => {
  if (!(await fileExists(dir))) {
    try {
      await fs.mkdir(dir)
    } catch (_) {}
  }

  if (!(await fileExists(file))) {
    await fs.writeFile(file, JSON.stringify({}))
  }
}

const readJSONFile = (path: string) =>
  Bun.file(path).json() as Promise<Record<string, string>>

async function main() {
  // TODO: Make dynamic when Bun supports reading files from directory
  // const sourceFiles: string[] = await fs.readdir(ENGLISH_BASE)
  const sourceFiles = ["translation.json", "auth.json"]
  sourceFiles.forEach(async (sourceFile) => {
    // const sourcePhrases = JSON.parse(
    //   await fs.readFile(`${ENGLISH_BASE}/${sourceFile}`, "utf8"),
    // ) as Record<string, string>
    const sourcePhrases = await readJSONFile(`${ENGLISH_BASE}/${sourceFile}`)

    targetLanguages.forEach(async (targetLanguage) => {
      const targetDir = `${SOURCE_BASE}/${targetLanguage.code}`
      const targetFile = `${targetDir}/${sourceFile}`

      await ensureLanguageFileExists(targetDir, targetFile)
      const targetPhrases = await readJSONFile(targetFile)
      // const targetPhrases = JSON.parse(
      //   await fs.readFile(targetFile, "utf8"),
      // ) as Record<string, string>

      // Delete phrases from "en" version to have them deleted from all others
      const deletePhrases = difference(
        Object.keys(targetPhrases),
        Object.keys(sourcePhrases),
      )

      if (deletePhrases.length) {
        console.log("Deleting phrases:", deletePhrases.join(", "))
        deletePhrases.forEach((phrase) => delete targetPhrases[phrase])
        // await fs.writeFile(targetFile, JSON.stringify(targetPhrases, null, 2))
        await Bun.write(targetFile, JSON.stringify(targetPhrases, null, 2))
      }

      const missingPhrases = difference(
        Object.keys(sourcePhrases),
        Object.keys(targetPhrases),
      )

      if (!missingPhrases.length) return

      console.log({ missingPhrases })

      // console.log("Translating phrases:", missingPhrases.join(", "))

      const runTranslation = async (key: string) => {
        const value = sourcePhrases[key] || ""
        try {
          const [translation] = await translateClient.translate(value, {
            from: "en",
            to: targetLanguage.code,
          })

          console.log({ translation })

          // Remove extra spaces to HTML added by Translation API
          targetPhrases[key] = translation.replaceAll(/\>\s/g, ">")
        } catch (err) {
          console.error(err)
        }
      }

      // const translations$ = missingPhrases.map(runTranslation);

      while (missingPhrases.length) {
        console.log(
          `    Running batch translation for ${targetLanguage.code}: ${
            ~~(missingPhrases.length / TRANSLATION_BATCH_SIZE) + 1
          } batches left`,
        )

        await Promise.all(
          missingPhrases.splice(0, TRANSLATION_BATCH_SIZE).map(runTranslation),
        )
      }

      console.log({ targetPhrases })

      // await fs.writeFile(targetFile, JSON.stringify(targetPhrases, null, 2))
      // await Bun.write(targetFile, JSON.stringify(targetPhrases, null, 2))
    })
  })
}

main().catch((error) => console.error(error))
